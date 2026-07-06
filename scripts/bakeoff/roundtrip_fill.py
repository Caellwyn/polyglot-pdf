#!/usr/bin/env python3
"""True round-trip fill-back harness (bd polyglot-pdf-7a9.14).

The bake-off scorer (scripts/schema_score.py) grades a draft schema by matching
pdf_field_names against the gold -- a PROXY for fill-ability. For TEXT fields the
name+type proxy is sound, but for CHECKBOX/RADIO it is NOT: the production filler
(backend/routes/pdf_fill_routes.py) selects the widget by matching the VALUE the
app sends against option.value, then writes option.pdf_field_name. A schema can
score green on names yet fail a real fill (wrong option.value, missed
consolidation, un-unlocked read-only widget).

This harness closes that gap. It feeds a schema + a synthetic full-coverage value
set through the EXACT widget-write semantics of the production filler, saves the
PDF, RE-OPENS it, and asserts each targeted widget actually received its value.
It reports a HARD per-schema choice_fill_success = filled/attempted for
checkbox+radio SEPARATELY from text.

Fidelity to production: the fill calls below are copied VERBATIM (semantics, not
prose) from backend/routes/pdf_fill_routes.py as of 2026-07-05 (bd h76m.17 parity) --
  - text     : widget.field_value = str(value); widget.update()
  - checkbox/radio: widget.field_value = on_state; doc.xref_set_key(xref,"AS","/on")
                    (NO update() -- XFA viewer regenerates appearance)
  - checkbox_group (v2): shares the checkbox branch -- EVERY selected option's own
                    pdf_field_name is its widget; field-level pdf_field_name is
                    FORBIDDEN on a v2 group (form_models.py _collect_v2_problems)
  - shared-field radio (v2): an option with only pdf_on_value (no own
                    pdf_field_name) resolves against the FIELD-level
                    pdf_field_name -- one AcroForm field, several kid widgets
                    told apart by on-state; write is a direct xref V+AS to
                    the chosen kid, no get_button_on_state/update()
  - find_widget : exact field_name, then endswith fallback (XFA full path)
  - find_widget_by_state : same name-match, but returns the KID whose /AP
                    normal states include the given on-state (strict, no
                    'Yes' default -- a broken sibling must never masquerade)
  - get_button_on_state : first non-Off 'normal' state, else "Yes"
  - read-only unlock : conditional_behavior.pdf_field_flag_change bit flip
If the production filler changes, update this file (it deliberately does NOT import
the route -- the route's logic is nested inside a FastAPI handler + async store).

VERIFICATION read-back (probed on I-90, PyMuPDF 1.24): after save+reopen, a
checkbox's field_value reads back EMPTY -- its state lives in the /AS xref key
(xref_get_key(xref,"AS") == ('name','/<on>')). So checkbox/radio are verified via
/AS, text via field_value.

ASCII only (cp1252 safe). Usage:
    python scripts/bakeoff/roundtrip_fill.py --schema SCHEMA.json --pdf FORM.pdf \
        [--json OUT.json] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from typing import Any, Optional

import fitz  # PyMuPDF


# --------------------------------------------------------------------------- #
# Production-faithful widget write helpers (mirrors pdf_fill_routes.py)
# --------------------------------------------------------------------------- #

# A shared-field radio on-state goes into a RAW /Name token; production
# (pdf_fill_routes.py _PDF_NAME_UNSAFE, bd h76m.17) REFUSES to write one carrying
# PDF-Name-unsafe characters, counting the field as skipped/unfilled. The harness
# mirrors that exact charset AND its SCORING: an unsafe on-state is recorded in
# run() as an attempted-but-unfilled write (stays in the denominator), never
# dropped (which would make the field vanish and inflate the fill rate;
# bd polyglot-pdf-bvmu).
_PDF_NAME_UNSAFE = re.compile(r"[\s/#()<>\[\]{}%]")


def _pdf_name_unescape(s: Optional[str]) -> str:
    """Decode PDF name #XX hex escapes (e.g. '#20APT#20' -> ' APT ').

    PyMuPDF returns a written /AS on-state with #XX escapes decoded, while
    button_states() reports the raw escaped form -- so the two must be normalized
    to the same (decoded) space before an equality check.
    """
    if not s:
        return ""
    return re.sub(r"#([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), s)


def _get_button_on_state(widget) -> str:
    """First non-Off 'normal' appearance state, else 'Yes' (route line ~83)."""
    try:
        states = widget.button_states() or {}
        normal = states.get("normal")
        if isinstance(normal, list):
            for s in normal:
                if s and s.lower() not in {"off", ""}:
                    return s
    except Exception:
        pass
    return "Yes"


def _find_widget(doc, field_name: str):
    """Exact field_name match, then endswith fallback (route line ~148)."""
    for pno in range(doc.page_count):
        page = doc[pno]
        for w in page.widgets() or []:
            if w.field_name == field_name:
                return w, page
    for pno in range(doc.page_count):
        page = doc[pno]
        for w in page.widgets() or []:
            if w.field_name and w.field_name.endswith(field_name):
                return w, page
    return None, None


def _is_button(widget) -> bool:
    return widget.field_type == 2 or widget.field_type_string in {"CheckBox", "RadioButton"}


def _widget_has_on_state(widget, on_state: str) -> bool:
    """STRICT membership check: on_state appears in the widget's /AP normal
    states (route line ~191). No 'Yes' default -- an empty/broken appearance
    table means NOT-a-match, never a masquerading sibling kid."""
    try:
        states = widget.button_states() or {}
        normal = states.get("normal") or []
        return isinstance(normal, list) and on_state in normal
    except Exception:
        return False


def _find_widget_by_state(doc, field_name: str, on_state: str):
    """Find the radio KID matching an 'on' appearance state (route line ~205).

    A true-AcroForm radio group is ONE field name shared by several kid
    widgets, each distinguished only by its on-state. Falls back to the first
    name-match so an unexpected appearance table still resolves something.
    """
    fallback = (None, None)
    for pno in range(doc.page_count):
        page = doc[pno]
        for widget in page.widgets() or []:
            name = widget.field_name or ""
            if name == field_name or name.endswith(field_name):
                if fallback == (None, None):
                    fallback = (widget, page)
                if _widget_has_on_state(widget, on_state):
                    return (widget, page)
    return fallback


def _fill_widget(doc, page, widget, value) -> None:
    """Write a value to a widget exactly as the route does (route line ~101).

    Re-fetch a fresh widget off the page first (weak-reference guard).
    """
    fresh = None
    for w in page.widgets() or []:
        if w.field_name == widget.field_name:
            fresh = w
            break
    if not fresh:
        return
    if _is_button(fresh):
        if value in {True, "true", "True", "1", 1}:
            target = _get_button_on_state(fresh)
        elif value in {False, "false", "False", "0", 0}:
            target = "Off"
        else:
            target = str(value)
        fresh.field_value = target
        doc.xref_set_key(fresh.xref, "AS", f"/{target}")
    else:
        fresh.field_value = str(value)
        fresh.update()


def _apply_flag_unlock(widget, conditional_behavior: Optional[dict]) -> None:
    """Flip a read-only bit if conditional_behavior asks for it (route line ~176)."""
    if not conditional_behavior:
        return
    change = conditional_behavior.get("pdf_field_flag_change")
    if not change:
        return
    try:
        current = widget.field_flags
        bit = change.get("bit", 0)
        cur_val = change.get("current_value", 1)
        req_val = change.get("required_value", 0)
        if (current >> bit) & 1 == cur_val:
            if req_val == 0:
                widget.field_flags = current & ~(1 << bit)
            else:
                widget.field_flags = current | (1 << bit)
            widget.update()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Synthetic full-coverage value set (value SHAPES per bd 7a9.14 #4)
# --------------------------------------------------------------------------- #

def synth_value(field: dict) -> Any:
    """A representative value for a field, in the shape the filler/frontend expect.

    - radio                       -> a single option.value (widget leaf string)
    - checkbox WITH options       -> a string[] of EVERY option.value (exercise all)
    - checkbox_group (v2)         -> a string[] of EVERY option.value (exercise all)
    - single checkbox (no options)-> True (boolean)
    - text/date/number/textarea   -> a string
    """
    ftype = field.get("type")
    opts = field.get("options") or []
    if ftype == "radio":
        return opts[0].get("value") if opts else None
    if ftype in ("checkbox", "checkbox_group"):
        if opts:
            return [o.get("value") for o in opts if o.get("value") is not None]
        return True
    if ftype in ("text", "textarea", "date", "number", "select"):
        if ftype == "select" and opts:
            return opts[0].get("value")
        return "RT"
    return None


# --------------------------------------------------------------------------- #
# Fill + verify
# --------------------------------------------------------------------------- #

def _target_widgets_for_field(field: dict) -> list[tuple[str, str]]:
    """The (pdf_field_name, expected) widget writes a fully-selected field implies.

    Returns a list of (widget_name, kind) where kind is 'choice' or 'text'.
    For a radio/checkbox the targets are the option-level pdf_field_names that the
    synth value selects; for a single checkbox / text it is the field-level name.

    v2 (bd h76m.17) mirrors backend/routes/pdf_fill_routes.py's two group shapes:
      - checkbox_group: shares the checkbox branch -- EVERY selected option's
        pdf_field_name is its own widget (field-level pdf_field_name is FORBIDDEN
        on a v2 group, per form_models.py's _collect_v2_problems).
      - shared-field radio: an option with NO pdf_field_name of its own, only
        pdf_on_value, resolves against the FIELD-level pdf_field_name -- one
        AcroForm field shared by several kid widgets, distinguished by on-state.
        The widget "name" returned here is a synthetic f"{field_name}\x00{on_value}"
        marker (kind 'choice_shared') so _find_widget can route it to the
        state-matching kid instead of a plain name lookup.
    """
    ftype = field.get("type")
    opts = field.get("options") or []
    val = synth_value(field)
    targets: list[tuple[str, str]] = []
    if ftype == "radio":
        sel = next((o for o in opts if o.get("value") == val), None)
        if sel:
            if sel.get("pdf_field_name"):
                targets.append((sel["pdf_field_name"], "choice"))
            elif sel.get("pdf_on_value") and field.get("pdf_field_name"):
                # Emit the shared-radio target even when the on-state is
                # PDF-Name-unsafe: the unsafe case is handled in run() as an
                # ATTEMPTED-but-unfilled write (production refuses it and counts
                # the field as skipped/unfilled -- it stays in the denominator),
                # NOT by dropping the target here (which would make the field
                # VANISH from scoring and inflate the fill rate; bd bvmu).
                marker = f"{field['pdf_field_name']}\x00{sel['pdf_on_value']}"
                targets.append((marker, "choice_shared"))
    elif ftype in ("checkbox", "checkbox_group"):
        if opts:
            selected = set(val or [])
            for o in opts:
                if o.get("value") in selected and o.get("pdf_field_name"):
                    targets.append((o["pdf_field_name"], "choice"))
        else:
            name = field.get("pdf_field_name")
            if name:
                targets.append((name, "choice"))
    else:  # text-like
        name = field.get("pdf_field_name")
        if name:
            targets.append((name, "text"))
    return targets


def _widget_leaf(name: Optional[str]) -> Optional[str]:
    """The dotted leaf of a widget name, e.g. 'form1[0].#subform[0].X[0]' -> 'X[0]'."""
    if not name:
        return None
    return name.split(".")[-1]


def score_value_convention(schema: dict) -> dict:
    """Does each choice option.value follow the canonical widget-leaf convention?

    Round-trip fill of a checkbox/radio mechanically succeeds as long as
    option.pdf_field_name resolves to a widget -- but PRODUCTION selection also
    needs option.value to be the value the app actually sends, and on I-90 that is
    the WIDGET-LEAF identifier (RadioField.tsx emits option.value; the filler
    matches it; controls_fields[].value references the same string). An arm that
    invents a SEMANTIC value ("white", "male") fills in this harness's closed loop
    but breaks real selection + conditional logic.

    Test (deterministic): option.value must equal the widget leaf of its own
    option.pdf_field_name (exact, or the leaf with/without a trailing [n]). This is
    the bd 7a9.14 rule #1 conformance check, independent of fill mechanics.
    """
    total = conforming = 0
    violations = []
    for f in schema.get("fields", []):
        if f.get("type") not in ("radio", "checkbox", "checkbox_group"):
            continue
        for o in (f.get("options") or []):
            pfn = o.get("pdf_field_name")
            val = o.get("value")
            if not pfn or val is None:
                continue
            total += 1
            leaf = _widget_leaf(pfn)
            val_s = str(val)
            # Conforms ONLY if value IS the widget leaf, or the leaf stripped of
            # its trailing [n] index (some schemas drop the index on the value).
            # A bare suffix match (e.g. value "[0]") must NOT count -- that would
            # falsely inflate the metric the check exists to protect.
            leaf_noidx = leaf.rsplit("[", 1)[0] if leaf and "[" in leaf else leaf
            if val_s and (val_s == leaf or val_s == leaf_noidx):
                conforming += 1
            else:
                violations.append({"field_id": f.get("id"), "value": val_s,
                                   "widget_leaf": leaf})
    # pct is None (not NaN) when nothing applies -- NaN serializes to the invalid
    # JSON token "NaN" that strict parsers (e.g. JS JSON.parse) reject.
    pct = (100.0 * conforming / total) if total else None
    return {"total": total, "conforming": conforming, "pct": pct,
            "violations": violations}


def run(schema_path: str, pdf_path: str, verbose: bool = False) -> dict:
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    fields = schema.get("fields", [])

    doc = fitz.open(pdf_path)

    # Plan + apply the writes, recording what we EXPECT each widget to hold.
    # expected[widget_name] = ("choice", on_state) | ("text", "RT")
    #   | ("choice", on_state, shared_field_name)  -- v2 shared-field radio,
    #     keyed "xref:{n}" since sibling kids share one field_name.
    expected: dict[str, tuple] = {}
    attempts: list[dict] = []  # one per (field, widget) target

    for field in fields:
        fid = field.get("id")
        ftype = field.get("type")
        cbeh = field.get("conditional_behavior")
        for widget_name, kind in _target_widgets_for_field(field):
            if kind == "choice_shared":
                # Shared-field radio (bd h76m.17): widget_name is the
                # f"{field_pdf_name}\x00{on_value}" marker built above --
                # resolve it against the STATE-matching kid (route's
                # find_widget_by_state), never a plain name lookup (every kid
                # shares the same field_name, so name-only would grab the
                # wrong sibling).
                shared_field, on_state = widget_name.split("\x00", 1)
                # Production (pdf_fill_routes.py _PDF_NAME_UNSAFE, bd h76m.17)
                # REFUSES to write an on-state carrying PDF-Name-unsafe chars,
                # counting the field as skipped/unfilled. Mirror the SCORING, not
                # just the refusal: record an ATTEMPTED-but-unfilled write (like
                # the widget-not-found path below) so the field stays in the
                # denominator -- dropping the target instead would make it vanish
                # and inflate the fill rate (bd polyglot-pdf-bvmu, fresh-eyes r2).
                if _PDF_NAME_UNSAFE.search(on_state):
                    attempts.append({"field_id": fid, "field_type": ftype,
                                     "widget": f"{shared_field}[on={on_state}]",
                                     "kind": kind, "found": False,
                                     "refused_unsafe_on_state": True})
                    continue
                widget, page = _find_widget_by_state(doc, shared_field, on_state)
                rec = {"field_id": fid, "field_type": ftype,
                       "widget": f"{shared_field}[on={on_state}]",
                       "kind": kind, "found": bool(widget)}
                if not widget:
                    attempts.append(rec)
                    continue
                _apply_flag_unlock(widget, cbeh)
                # Direct xref write (route line ~359): V + AS to the on_state,
                # NO fill_widget/get_button_on_state -- the state IS the value.
                doc.xref_set_key(widget.xref, "V", f"/{on_state}")
                doc.xref_set_key(widget.xref, "AS", f"/{on_state}")
                # Keyed by xref, not field_name: sibling kids of the same
                # shared field all carry the SAME field_name, so a
                # field_name-keyed expectation would collide/overwrite. The
                # shared field name travels alongside so read-back only
                # searches that field's own kids (never a different shared
                # group that happens to reuse the same on-state string).
                expected[f"xref:{widget.xref}"] = ("choice", on_state, shared_field)
                rec["resolved_widget"] = f"xref:{widget.xref}"
                attempts.append(rec)
                continue

            widget, page = _find_widget(doc, widget_name)
            rec = {"field_id": fid, "field_type": ftype, "widget": widget_name,
                   "kind": kind, "found": bool(widget)}
            if not widget:
                attempts.append(rec)
                continue
            _apply_flag_unlock(widget, cbeh)
            if kind == "choice":
                on = _get_button_on_state(widget) if _is_button(widget) else "Yes"
                _fill_widget(doc, page, widget, True)
                expected[widget.field_name] = ("choice", on)
            else:
                _fill_widget(doc, page, widget, "RT")
                expected[widget.field_name] = ("text", "RT")
            rec["resolved_widget"] = widget.field_name
            attempts.append(rec)

    # NamedTemporaryFile (not mktemp) avoids the TOCTOU race, matching the
    # production filler. ONE outer try/finally guards os.remove(tmp) across BOTH
    # the save and the re-open, so the temp file is cleaned up even if doc.save()
    # raises; an inner finally guarantees doc.close().
    verified: dict[str, bool] = {}
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
        tmp = tf.name
    try:
        try:
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()

        # Re-open and verify each expected widget actually holds its value.
        d2 = fitz.open(tmp)
        # Index widgets by exact name for read-back. A shared-field radio's
        # kids all carry the SAME name, so this maps to a LIST -- xrefs are
        # not trusted to survive save()'s garbage collection/renumbering, so
        # "xref:{n}" entries are resolved by re-matching name + on-state
        # below rather than by xref lookup.
        by_name: dict[str, list] = {}
        for pno in range(d2.page_count):
            for w in d2[pno].widgets() or []:
                by_name.setdefault(w.field_name, []).append(w)
        for wname, entry in expected.items():
            if wname.startswith("xref:"):
                # 3-tuple: (kind, on_state, shared_field_name). want == the
                # on_state; find it ONLY among that shared field's own kids
                # (name exact-or-endswith, same convention as _find_widget),
                # by whichever kid's /AS now reads that state.
                kind, want, shared_field = entry
                w = None
                for name, candidates in by_name.items():
                    if not (name == shared_field or name.endswith(shared_field)):
                        continue
                    for cand in candidates:
                        as_key = d2.xref_get_key(cand.xref, "AS")
                        as_val = as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
                        norm = as_val[1:] if isinstance(as_val, str) and as_val.startswith("/") else as_val
                        if norm and _pdf_name_unescape(norm) == _pdf_name_unescape(want):
                            w = cand
                            break
                    if w:
                        break
            else:
                kind, want = entry
                candidates = by_name.get(wname) or []
                w = candidates[0] if candidates else None
            if not w:
                verified[wname] = False
                continue
            if kind == "choice":
                # Checkbox/radio state persists in /AS, not field_value (probed).
                # Assert the EXACT expected on-state ("want"), not merely non-Off,
                # so a wrong appearance state is caught. Compare UNESCAPED: a PDF
                # name escapes special chars as #XX (e.g. on-state "#20APT#20"
                # reads back as "/ APT "), so decode both sides before comparing.
                as_key = d2.xref_get_key(w.xref, "AS")
                as_val = as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
                norm = as_val[1:] if isinstance(as_val, str) and as_val.startswith("/") else as_val
                verified[wname] = (bool(norm) and norm not in ("Off", "null")
                                   and _pdf_name_unescape(norm) == _pdf_name_unescape(want))
            else:
                verified[wname] = (w.field_value or "") == want
        d2.close()
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    # Tally, split choice vs text. "choice_shared" (v2 shared-field radio
    # kids) counts under the CHOICE bucket -- it is a checkbox/radio fill,
    # just resolved by on-state instead of a per-option pdf_field_name.
    def tally(kind: str) -> dict:
        kinds = {"choice", "choice_shared"} if kind == "choice" else {kind}
        recs = [a for a in attempts if a["kind"] in kinds]
        attempted = len(recs)
        filled = 0
        for a in recs:
            rw = a.get("resolved_widget")
            if rw and verified.get(rw):
                filled += 1
        return {"attempted": attempted, "filled": filled,
                "pct": (100.0 * filled / attempted) if attempted else None}

    choice = tally("choice")
    text = tally("text")

    # Per-attempt failure detail for triage.
    failures = []
    for a in attempts:
        rw = a.get("resolved_widget")
        ok = bool(rw and verified.get(rw))
        if not ok:
            if a.get("refused_unsafe_on_state"):
                reason = "refused_unsafe_on_state"  # production skips this too
            elif not a["found"]:
                reason = "widget_not_found"
            else:
                reason = "value_not_set"
            failures.append({
                "field_id": a["field_id"], "field_type": a["field_type"],
                "widget": a["widget"], "kind": a["kind"],
                "reason": reason,
            })

    value_conv = score_value_convention(schema)

    result = {
        "schema": schema_path, "pdf": pdf_path,
        "choice_fill_success": choice,   # checkbox + radio (mechanical fill)
        "text_fill_success": text,
        "value_convention": value_conv,  # option.value == widget-leaf (rule #1)
        "failures": failures,
    }
    if verbose:
        result["attempts"] = attempts
    return result


def _fmt(t: dict) -> str:
    p = t["pct"]
    ps = "  n/a" if p is None else f"{p:5.1f}%"
    return f"{ps}  ({t['filled']}/{t['attempted']})"


def _fmt_conv(c: dict) -> str:
    p = c["pct"]
    ps = "  n/a" if p is None else f"{p:5.1f}%"
    return f"{ps}  ({c['conforming']}/{c['total']})"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="True round-trip fill-back harness (7a9.14).")
    ap.add_argument("--schema", required=True, help="draft or gold FormSchema JSON")
    ap.add_argument("--pdf", required=True, help="the source PDF to fill")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--verbose", action="store_true", help="include per-attempt detail")
    args = ap.parse_args(argv)

    result = run(args.schema, args.pdf, verbose=args.verbose)
    print("=" * 60)
    print(f"ROUND-TRIP FILL: {os.path.basename(args.schema)}")
    print("=" * 60)
    print(f"  CHOICE (checkbox+radio) fill success: {_fmt(result['choice_fill_success'])}")
    print(f"  TEXT                    fill success: {_fmt(result['text_fill_success'])}")
    print(f"  CHOICE value-convention (opt.value==leaf): {_fmt_conv(result['value_convention'])}")
    vc = result["value_convention"]
    if vc["violations"]:
        print(f"  value-convention violations ({len(vc['violations'])}):")
        for v in vc["violations"][:12]:
            print(f"    {v['field_id']}: value={v['value']!r} != leaf {v['widget_leaf']!r}")
        if len(vc["violations"]) > 12:
            print(f"    ... +{len(vc['violations']) - 12} more")
    if result["failures"]:
        print(f"  failures ({len(result['failures'])}):")
        for f in result["failures"][:25]:
            print(f"    [{f['kind']}] {f['field_id']} ({f['field_type']}) "
                  f"{f['widget']} -- {f['reason']}")
        if len(result["failures"]) > 25:
            print(f"    ... +{len(result['failures']) - 25} more")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print(f"[wrote {args.json_out}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
