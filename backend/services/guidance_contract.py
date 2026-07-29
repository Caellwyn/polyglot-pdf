"""Guidance content contract (bd polyglot-pdf-wsao.3; sprint-16 plan).

ONE module owns the rules for the two guidance channels the instructions-
enrichment epic bakes into form kits (help.instructions -- short abstractive
overview; help.details -- verbatim official-booklet excerpts), mirroring the
render-once pattern of scripts/bakeoff/schema_contract.py. Three consumers:

  1. the enrichment prompt (wsao.4 engine) renders CONTRACT_TEXT verbatim;
  2. the judge prompt (wsao.5 verify loop) scores against the same text;
  3. schema_lint's deterministic rules import the bounds + normalization
     helpers below, so the mechanical checks and the prompts can never drift
     apart.

The containment check is the ZERO-TRUST core of the details channel (plan:
"SELECT-not-REWRITE"): every details paragraph must appear verbatim -- modulo
the PINNED normalization below -- inside the booklet reference text the
schema itself carries (metadata.booklet_text, the secretary floor shipped by
bd wsao.1). Fabrication is therefore structurally impossible; only
mis-scoping survives, which the judge + human review check.

Normalization spec (pinned HERE; loosening it re-admits paraphrase, so any
change is a contract change):
  - unicode punctuation folded to ASCII (curly quotes/apostrophes, en/em
    dashes, non-breaking space);
  - line-break hyphenation joined ("with-\\nholding" -> "withholding");
  - every whitespace run collapsed to one space;
  - casefolded.
Match = exact substring of the normalized source. No similarity scores: a
deterministic yes/no with a recorded matched span beats a tunable fuzz that
would slowly readmit rewriting.

KNOWN false-positive mode of the pinned dehyphenation (wsao.3 fresh-eyes):
a legitimately hyphenated compound that wraps AT its hyphen in the source
("third-\\nparty") normalizes to "thirdparty", so a clean-typed excerpt
keeping "third-party" fails containment. Accepted tradeoff: the enrichment
engine copies from the SAME extracted source text that becomes the floor, so
both sides normalize identically in practice; hand-typed excerpts should be
pasted from the extraction, not re-typed.

Size bounds (sprint-16 plan; oversize policy DECIDED by the maintainer
2026-07-26, bd wsao.8):
  - instructions: soft <= INSTRUCTIONS_SOFT_CHARS (speakable ask-tail), hard
    INSTRUCTIONS_HARD_CHARS (lint WARNING above it);
  - details: up to DETAILS_INLINE_MAX_CHARS ride the voice model INLINE while
    the field is focused (lint WARNING above it; clamp_details_inline is the
    render backstop). The enrichment engine authors to fit via SELECTION +
    INDEX -- verbatim excerpts up to budget plus a one-line index of dropped
    topics -- never summarization, never blind truncation. The secretary
    always holds the FULL text (the booklet floor). The compression window
    derivation prices the inline injection in (inline_injection_budget_tokens
    -> derive_compression_window), which is what makes the budget viable: a
    details-bearing initiating message used to 1007 at session assemble
    (wsao.2 measurement; scripts/spikes/wsao2_inline_details_findings.md).

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import List, Optional

INSTRUCTIONS_SOFT_CHARS = 280
INSTRUCTIONS_HARD_CHARS = 500
# The INLINE guidance budget (bd wsao.8, maintainer decision 2026-07-26): up
# to this many characters of help.details ride the voice model's guidance
# block while the field is focused (~5k tokens; ~$0.005/encounter on live-2.5
# per the maintainer's math, measured in wsao.8). The schema + secretary
# always carry the FULL text; an oversize SOURCE is handled by the enrichment
# engine via SELECTION + INDEX (verbatim excerpts up to budget + a one-line
# index of dropped topics), never summarization (bake-time rewriting of legal
# text) and never blind truncation (the model must KNOW what it is missing).
# clamp_details_inline below is the defensive RENDER-time backstop for a kit
# that ships oversize anyway.
DETAILS_INLINE_MAX_CHARS = 20000
# Fixed slop the injection budget adds on top of the clamp: the clamp's
# appended topic-index tail can push the rendered injection slightly past
# max_chars (measured worst case ~+1.1k chars ~= 280 tokens; wsao.8
# fresh-eyes finding 3).
INJECTION_BUDGET_SLOP_TOKENS = 288
# A details block longer than this without any heading line is unnavigable
# for the secretary + human review (plan: "headings mandatory above a size
# threshold").
DETAILS_HEADINGS_REQUIRED_CHARS = 1500

# On-screen deixis / cross-references that make no sense in a spoken,
# model-facing channel (plan: no "see page 7", no screen deixis).
SCREEN_REF_RE = re.compile(
    r"(see\s+(page|the\s+instructions|instructions\s+for)|"
    r"\bon\s+page\s+\d|\babove\b|\bbelow\b|\bthis\s+page\b)",
    re.IGNORECASE,
)

# A heading line: markdown-style (## ...) or a lettered/numbered official
# heading ("a. Nonresident alien...", "Exception 1.", "Line 6d.").
_HEADING_LINE_RE = re.compile(
    r"^(#{1,4}\s+\S|[a-h]\.\s+\S|Exception\s+\d|Line\s+\d)", re.IGNORECASE)

# chr()-composed so this source stays pure ASCII (CLAUDE.md scar #6):
# 2018/2019/201A/201B curly apostrophes and 201C/201D/201E curly quotes fold
# to ASCII; 2013 en / 2014 em / 2212 minus fold to hyphen; 00A0/2007/2009/202F
# spaces fold to plain space.
_PUNCT_FOLD = {}
for _cp in (0x2018, 0x2019, 0x201A, 0x201B):
    _PUNCT_FOLD[chr(_cp)] = chr(39)
for _cp in (0x201C, 0x201D, 0x201E):
    _PUNCT_FOLD[chr(_cp)] = chr(34)
for _cp in (0x2013, 0x2014, 0x2212):
    _PUNCT_FOLD[chr(_cp)] = chr(45)
for _cp in (0x00A0, 0x2007, 0x2009, 0x202F):
    _PUNCT_FOLD[chr(_cp)] = chr(32)


def normalize_for_containment(text: str) -> str:
    """The PINNED normalization both sides of the containment check pass
    through. See the module docstring before changing anything here.

    wsao.4 additions (both PDF line-wrap/glyph artifacts, measured on the
    real w7 booklet -- the same class as dehyphenation, NOT a loosening
    toward paraphrase): bullet glyphs fold to "-" (models transliterate
    list bullets), and whitespace after a slash is dropped (the booklet
    wraps lines AFTER slashes: "citizen/\\nresident")."""
    if not text:
        return ""
    for src, dst in _PUNCT_FOLD.items():
        text = text.replace(src, dst)
    # bullet glyphs -> "-" (2022 bullet, 25CF black circle, 00B7 middle dot,
    # F0B7 the Symbol-font private-use bullet PDFs often emit)
    for cp in (0x2022, 0x25CF, 0x00B7, 0xF0B7):
        text = text.replace(chr(cp), "-")
    # join line-break hyphenation BEFORE whitespace collapse ("with-\nholding")
    text = re.sub(r"-\s*\n\s*", "", text)
    # join slash-wraps ("citizen/\nresident" -> "citizen/resident") --
    # NEWLINE-adjacent only, mirroring the dehyphenation rule above; an
    # unconditional post-slash collapse would equate textually-distinct
    # sources like "and/ or" vs "and/or" (wsao.4 outer review).
    text = re.sub(r"/\s*\n\s*", "/", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


@dataclass(frozen=True)
class ContainmentResult:
    contained: bool
    # start offset of the match in the NORMALIZED source (-1 when absent) --
    # the "recorded matched span" the sprint-16 review required, so a human
    # can jump to the source passage instead of re-searching the booklet.
    matched_at: int
    matched_span: str  # normalized matched text ("" when absent)


def check_containment(paragraph: str, source_text: str) -> ContainmentResult:
    """Is `paragraph` a verbatim (normalized) excerpt of `source_text`?

    Convenience single-shot form. HOT LOOPS (lint over many details-bearing
    fields against one booklet) must normalize the source ONCE and call
    check_containment_normalized -- re-normalizing an 80KB+ booklet per
    paragraph per field is quadratic and measurably slows the hosted lint
    route (wsao.3 outer review)."""
    return check_containment_normalized(
        paragraph, normalize_for_containment(source_text))


def check_containment_normalized(
        paragraph: str, normalized_source: str) -> ContainmentResult:
    """check_containment against a source ALREADY passed through
    normalize_for_containment (the caller normalizes once per source)."""
    p = normalize_for_containment(paragraph)
    if not p:
        return ContainmentResult(True, -1, "")  # empty paragraph: vacuous
    idx = normalized_source.find(p)
    if idx < 0:
        return ContainmentResult(False, -1, "")
    return ContainmentResult(True, idx, p)


_FURNITURE_LINE_RE = re.compile(
    r"^(\d{1,3}|CAUTION|TIP|!|Instructions for Form [A-Z0-9-]+.*)$")


def clean_booklet_furniture(text: str) -> str:
    """Strip PDF page furniture from extracted booklet text: sidebar glyph
    labels (CAUTION / TIP / !), bare page numbers, and the running
    'Instructions for Form X-N (Rev. ...)' footer. The raw extraction
    interleaves these MID-SENTENCE in the text stream (wsao.4, measured on
    the real w7 booklet), so a model's correctly-copied logical sentence
    fails containment against the raw stream. BOTH sides must use the
    cleaned text: the enrichment engine excerpts from it AND bakes it as the
    metadata.booklet_text floor, so containment stays consistent."""
    if not isinstance(text, str):  # never-throws contract (module siblings)
        return ""
    out = []
    for ln in (text or "").splitlines():
        if _FURNITURE_LINE_RE.match(ln.strip()):
            continue
        out.append(ln)
    return "\n".join(out)


def details_paragraphs(details: str) -> List[str]:
    """Split a details block into the paragraphs the containment check runs
    over: blank-line delimited, heading lines EXCLUDED (headings are the
    enrichment engine's own organizational scaffolding, not booklet text)."""
    out: List[str] = []
    for raw in re.split(r"\n\s*\n", details or ""):
        para = raw.strip()
        if not para:
            continue
        lines = [ln for ln in para.splitlines()
                 if not _HEADING_LINE_RE.match(ln.strip()) or len(ln) > 120]
        body = "\n".join(lines).strip()
        if body:
            out.append(body)
    return out


def clamp_details_inline(details: str,
                         max_chars: int = DETAILS_INLINE_MAX_CHARS) -> str:
    """Defensive render-time clamp for the inline details budget (bd wsao.8).

    A details value within budget passes through UNTOUCHED (byte-identical).
    An oversize value is cut at the last paragraph boundary within budget and
    a one-line INDEX of the dropped topics (heading lines found in the
    remainder) is appended, so the voice model KNOWS what it is missing and
    that the secretary holds it -- the selection+index policy's backstop.
    """
    if not isinstance(details, str) or len(details) <= max_chars:
        return details
    cut = details.rfind("\n\n", 0, max_chars)
    if cut <= 0:
        cut = max_chars
    kept, dropped = details[:cut].rstrip(), details[cut:]
    topics = []
    for ln in dropped.splitlines():
        ln = ln.strip()
        if ln and _HEADING_LINE_RE.match(ln) and len(ln) <= 120:
            topics.append(ln.lstrip("#").strip().rstrip("."))
    index = ("; ".join(topics[:8])) if topics else "additional official guidance"
    return (kept + "\n\n[Reference text continues -- the secretary holds the "
            "full official instructions, including: " + index + ". Ask the "
            "secretary when the answer is not above.]")


def inline_injection_budget_tokens(schema: dict) -> int:
    """The compression-window headroom (in ~tokens) the LARGEST per-field
    inline guidance injection needs for this schema: max over fields of the
    CLAMPED details length, chars/4. 0 when no field carries details -- the
    window derivation then stays byte-identical to pre-wsao.8 behavior."""
    worst = 0
    for f in schema.get("fields") or []:
        if not isinstance(f, dict):
            continue
        h = f.get("help")
        d = h.get("details") if isinstance(h, dict) else None
        if isinstance(d, str) and d.strip():
            worst = max(worst, min(len(d), DETAILS_INLINE_MAX_CHARS))
    if worst == 0:
        return 0
    # + slop for the clamp's appended topic-index tail (see the constant).
    return worst // 4 + INJECTION_BUDGET_SLOP_TOKENS


def has_heading(details: str) -> bool:
    return any(_HEADING_LINE_RE.match(ln.strip())
               for ln in (details or "").splitlines())


def is_label_restatement(instructions: str, name: Optional[str],
                         option_labels: List[str]) -> bool:
    """True when instructions add nothing beyond the field's own label and
    option labels (plan: anti-restatement). Normalized comparison: the
    instructions text, minus the label/option words and filler verbs, must
    leave some residue to count as guidance.

    Coerces non-string inputs (raw LLM drafts carry lists/numbers where
    strings belong) -- callers sit inside lint's never-throws contract."""
    if not isinstance(instructions, str):
        return False
    name = name if isinstance(name, str) else ""
    option_labels = [l for l in option_labels if isinstance(l, str)]
    instr = normalize_for_containment(instructions)
    if not instr:
        return False
    label_blob = normalize_for_containment(
        " ".join([name or ""] + list(option_labels)))
    residue = instr
    for token in label_blob.split():
        # word-boundary, not substring: a one-letter label token ("a") must
        # not blank every 'a' inside real guidance (wsao.3 outer review)
        residue = re.sub(r"\b" + re.escape(token) + r"\b", " ", residue)
    residue = re.sub(
        r"\b(select|enter|choose|your|the|a|an|please|type|check|one|box)\b",
        " ", residue)
    residue = re.sub(r"[^a-z0-9]+", "", residue)
    return len(residue) < 8


CONTRACT_TEXT = """GUIDANCE CONTENT CONTRACT (sprint-16; bd wsao.3)

Two channels per field, distinct jobs:

help.instructions -- SHORT ABSTRACTIVE OVERVIEW (the only rewritten text).
- 2-4 sentences, aim <= 280 characters (hard lint bound 500). It is SPOKEN
  when the field is asked, so: English, second person, speakable prose. No
  markdown, no "see page 7" / "see the instructions", no on-screen deixis
  (above/below/this page).
- Content priority: (1) what value goes here and where the user finds it;
  (2) applicability conditions NOT already modeled as show_if -- never
  restate modeled conditions; (3) headline pitfalls/interlocks; (4) format
  only when help.format_hint cannot carry it.
- Ground EVERY claim in the official booklet text, the form's printed text,
  or the field's /TU tooltip. No outside legal knowledge. If the sources say
  nothing beyond the label, emit NOTHING -- empty beats filler, and a
  restatement of the label is a lint finding.

help.details -- VERBATIM OFFICIAL EXCERPTS (zero-trust channel).
- SELECT, never rewrite: copy the booklet passages relevant to this field
  word-for-word. Every paragraph must survive a mechanical containment check
  against the booklet text (normalization: quote folding, dehyphenation,
  whitespace collapse, case). A dropped qualifying clause ("unless...",
  "except...") adjacent to a selected passage is a judge finding.
- Organize under short heading lines (## or the booklet's own "a." /
  "Exception 1." headings) -- required above 1,500 characters.
- Do not leave cross-references dangling: excerpt the referenced passage too,
  or omit the sentence that points at it.
- Size: up to 20,000 characters ride the voice model inline while the field
  is focused (the compression window prices this in). When the relevant
  source exceeds that, SELECT the most load-bearing verbatim excerpts up to
  the budget and end with ONE line indexing the dropped topics by their
  headings ("The secretary also holds: ...") -- never summarize (no rewriting
  of legal text) and never cut silently. The secretary always holds the full
  text.
"""


# --------------------------------------------------------------------------- #
# Verify loop vocabulary (bd wsao.5). The judge rubric rendered into the
# judge prompt, and the flag taxonomy the bake persists at
# _bakeoff.authoring.instructions_enrich.flags (schema_lint re-emits these on
# every lint pass so the editor worklist needs zero extra plumbing --
# mirroring TRANSLATION_FLAG_RULES).
# --------------------------------------------------------------------------- #

GUIDANCE_FLAG_RULES = frozenset({
    # a field's authored text was revised by the bounded rectify loop and the
    # revision passed -- informational provenance for the human reviewer
    "instructions-rectified",
    # a field failed the judge even after rectify; its proposed text was
    # DROPPED and the deterministic baseline kept (the KEEP rule: never ship
    # unverified LLM legal text)
    "instructions-ungrounded-dropped",
    # the judge leg was unavailable (no credentials / API failure); NO
    # proposed text was written for the affected fields -- baseline kept
    "instructions-enrich-unavailable",
})

JUDGE_TEXT = """GUIDANCE JUDGE RUBRIC (sprint-16; bd wsao.5)

You are judging AI-authored per-field guidance for an official government
form against the form's OFFICIAL INSTRUCTIONS TEXT (provided verbatim). The
details channel is separately machine-checked for verbatim containment; your
job is what a mechanical check cannot see:

Per field, return a verdict object:
- grounded (bool): is EVERY claim in `instructions` traceable to the
  official text, the field's own digest (name/options/tooltip), or plain
  formatting fact? Outside legal knowledge or invented
  thresholds/dates/documents => false.
- unsupported_claims (list of short quotes): each claim you could not trace.
- useful_beyond_label (bool): does `instructions` tell the user anything
  beyond restating the field's label/options?
- omission_concerns (list of short notes): places where the SELECTED details
  excerpts drop an adjacent qualifying clause ("unless...", "except...",
  "only if...") whose absence makes the excerpt misleading.
- advice (bool): true if the text TELLS the user what to enter or which
  option to pick rather than explaining what the official text says
  (information-never-advice is a hard product rule).

A field passes when: grounded, useful_beyond_label (or instructions empty),
no advice, and no omission_concerns you judge material.
"""


# --------------------------------------------------------------------------- #
# Identity hashing for the staleness gate (bd polyglot-pdf-anim).
#
# Authored guidance is written against a field's VOICE-FACING identity. If a
# human later renames the field or relabels its options, the guidance may no
# longer match what the AI will say -- but a trivial rename does not warrant an
# LLM re-author. The bake records identity_sha1; lint recomputes it and flags a
# mismatch; the editor gates review-correct on a human acknowledgment.
#
# ONE definition, imported by BOTH the bake (enrich_instructions) and the lint
# rule, so the written hash and the compared hash can never drift apart. The
# option-translation re-run checker keys the same way in its own provenance
# stage and should import this rather than fork a second, subtly-different hash.
# --------------------------------------------------------------------------- #


def identity_payload(field: dict) -> str:
    """The stable serialization of a field's voice-facing identity.

    Covers ONLY what the guidance actually describes: the field's name, its
    spoken name, and its options -- each option contributing a
    [label, spoken_label, value] triple, so both voice-facing texts are BOUND
    to the option's stored value. spoken_label rides along because it
    OUTRANKS label as the voice join key (secretary_context resolves
    spoken_label or label; manifest_service ships it to the live model), so a
    spoken_label swap is the same wrong-answer hazard as a label swap
    (closeout Opus round 3, bd polyglot-pdf-w028). Deliberately excludes the
    field id (renames are retargeted wholesale and an id is never spoken) and
    plumbing (pdf_field_name, positions, conditions) -- changing those does
    not make authored guidance wrong, and hashing them would manufacture
    false staleness that trains editors to click through the gate.

    The triples are SORTED, so a pure REORDER (whole options moving, each
    keeping its own texts and value) does not re-raise the gate -- the
    assistant still says the same words (maintainer decision 2026-07-29).
    Adding, removing or editing a label or spoken label still flags.
    ACCEPTED TRADEOFF: guidance that describes option ORDER ("choose the
    first option") is not re-flagged by a reorder alone; the contract
    discourages that phrasing anyway.

    WHY the value rides in each binding (bd anim handoff decision): with
    bare sorted texts, a SWAP -- "Married" and "Single" trading places while
    their values stay put -- hashed identically, so the one identity drift
    that makes the assistant's unchanged words select a DIFFERENT stored
    answer never flagged. That is not stale wording; it is a wrong answer on
    the form. No order-insensitive hash can both ignore values and catch
    swaps (a swap IS a reorder plus a value rename), so the binding is the
    fix.

    SECOND ACCEPTED TRADEOFF, the flip side: a value-only rename (label
    untouched) now changes the hash and costs one acknowledgment click. The
    editor cannot produce that edit -- option values are minted from labels
    on blur, never free-typed (FieldEditor, bd h76m.10) -- so it lands only
    on out-of-band script/JSON edits, where a human glance is due anyway."""
    if not isinstance(field, dict):
        return "[]"
    opts = field.get("options")
    triples = []
    if isinstance(opts, list):
        for o in opts:
            lab = o.get("label") if isinstance(o, dict) else None
            slab = o.get("spoken_label") if isinstance(o, dict) else None
            val = o.get("value") if isinstance(o, dict) else None
            triples.append([
                lab if isinstance(lab, str) else "",
                slab if isinstance(slab, str) else "",
                # str() keeps numeric-value bindings distinct; "" would erase
                # them (labels coerce to "" -- a non-string label has no words
                # to bind, but a non-string value is still a real join key)
                val if isinstance(val, str) else
                ("" if val is None else str(val))])
    name = field.get("name")
    spoken = field.get("spoken_name")
    return json.dumps(
        [name if isinstance(name, str) else "",
         spoken if isinstance(spoken, str) else "",
         sorted(triples)],   # order-insensitive triples: see the docstring
        ensure_ascii=False, separators=(",", ":"))


def identity_sha1(field: dict) -> str:
    """SHA-1 of identity_payload -- the value stored in provenance and compared
    by the lint staleness rule."""
    return hashlib.sha1(
        identity_payload(field).encode("utf-8")).hexdigest()
