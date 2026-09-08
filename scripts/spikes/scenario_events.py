"""Scenario events + subsystem scoring for the full-system stress test
(bd polyglot-pdf-n86b, epic 00pt).

Turns the flat full-form question plan (full_form_script.py) into a STEP list
the measure_form_session_costs.py driver walks. A step is either a question
dict (back-compat: {field_id, say, wrong}, optionally flagged) or an event
dict discriminated by the "event" key:

  {"event": "recall", "say": ..., "expect_field_ids": [...],
   "expect_contains": ...}
      Mid-fill ask_secretary query. The driver speaks it, asserts the
      ask_secretary tool fired, and scores the delivered answer.

  {"event": "navigate_back", "say": ..., "target_field_id": ...,
   "correction_say": ..., "expected_after": ...}
      "Go back to X" -- the driver speaks it, waits (bounded) for the
      switch_to_field tool, answers the switch_field round-trip, speaks the
      correction, confirms, and asserts the target's post-state. Seam latency
      = utterance activity_end -> switch_field round-trip receipt.

Question-step FLAGS (set by weave_events, ride the question dict):
  "skip": True + "skip_say"      speak a skip request instead of the answer;
                                 assert skip_field recorded; expect-empty.
  "plant": {conflict_group, correct_say, expected_after}
      Speak a wrong-but-plausible value that forms a KNOWN contradiction.
      Detection is expected from a later validation pass; after a steer the
      driver runs a bounded steer window (switch_to_field -> correction ->
      confirm). expected_after replaces the field's expected canon.
  "path": "unhappy"              per-step path override (the E2 80/20 mix).

Event scripts are persona-tied (Linh Thi Nguyen, full_form_script answers):
STANDARD_EVENTS is the E2 "realistic session" script; UNHAPPY_PLANTS extends
the plant set for E3. REACTIVITY_SUITE defines the E4 short per-seam runs.

Scoring helpers at the bottom are pure functions over run records:
validator P/R against the planted groups (reusing backend/scripts/
g1b_scoring.py's prefix-tolerant group matching), latency percentiles, and
fill-failure mode classification (transcription / format / wrong-field /
missing / spurious).

Stdlib-only. ASCII only. Fictional persona, no real PII.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND_SCRIPTS = os.path.join(_REPO_ROOT, "backend", "scripts")
if _BACKEND_SCRIPTS not in sys.path:
    sys.path.insert(0, _BACKEND_SCRIPTS)

import g1b_scoring  # noqa: E402  (ids_match / _group_covered -- prefix-tolerant)


# --------------------------------------------------------------------------
# Event scripts (persona: Linh Thi Nguyen -- see full_form_script.py)
# --------------------------------------------------------------------------

# E2 "realistic session": interleaved recalls, corrections, one skip, two
# plants. after_field_id anchors an event AFTER that question's confirm.
STANDARD_EVENTS: list = [
    # The user forgets what they said their A-number was, two sections later.
    {"after_field_id": "ssn",
     "event": "recall",
     "say": "Wait, what did I say my alien registration number was earlier?",
     "expect_field_ids": ["a_number"],
     "expect_contains": "123456789"},
    # Cross-page recall while in Part 3.
    {"after_field_id": "p3_poe_city_state",
     "event": "recall",
     "say": "Can you check which city I gave for my mailing address?",
     "expect_field_ids": ["mail_city"],
     "expect_contains": "Houston"},
    # Navigate back and CHANGE a standalone field (no cross-field constraint,
    # so the correction cannot manufacture a validator conflict).
    {"after_field_id": "hair_color",
     "event": "navigate_back",
     "say": "Please go back to my mother's given name, I want to change it.",
     "target_field_id": "mother_given_name",
     "correction_say": "Her name should be Lan Anh.",
     "expected_after": "Lan Anh"},
    # Navigate back and RE-CONFIRM the same value (the "did I get that right"
    # flow -- measures the seam without changing state).
    {"after_field_id": "applicant_email",
     "event": "navigate_back",
     "say": "Go back to my street address for a moment, I want to check it.",
     "target_field_id": "mail_street",
     "correction_say": "Yes, it is four two zero zero Westheimer Road, that is right.",
     "expected_after": None},  # None = keep the plan's expected canon
    # The user cannot answer the USCIS account number -> voice skip
    # (replaces that question's fill; expect-empty via the skipped flag).
    {"field_id": "uscis_account",
     "event": "skip",
     "say": "I do not know my USCIS online account number, please skip it."},
    # Plant 1 (near pair, same page): Seattle ZIP against the Texas state.
    {"field_id": "mail_zip",
     "event": "plant",
     "planted_say": "My zip code is nine eight one zero one.",
     "conflict_group": ["mail_zip", "mail_state"],
     "correct_say": "Sorry, my zip code is seven seven zero two seven.",
     "expected_after": "77027"},
    # Plant 2 (far pair, page 1 vs page 7): the Part-8 continuation sheet's
    # copy of the A-Number contradicts the one given on page 1.
    #
    # REPLACES the pre-v2 plant, which paired the interpreter's language against
    # the applicant's (p6_language, page 4 vs 5). The applicant-only v2 kit drops
    # Part 6 entirely, so that pair cannot exist -- and the point of this plant is
    # the DISTANCE between the two mentions, not the interpreter specifically.
    # a_number -> p8_a_number is the widest span the kit still offers and is
    # copy_to-linked, so a mismatch between them is a real contradiction rather
    # than two unrelated answers.
    {"field_id": "p8_a_number",
     "event": "plant",
     "planted_say": "On the extra pages my A number is A zero eight seven six five four three two.",
     "conflict_group": ["a_number", "p8_a_number"],
     "correct_say": "Sorry, it is the same as before, one two three four five six seven eight nine.",
     "expected_after": "123456789"},
]

# E3 adds two more plants on top of STANDARD_EVENTS' two (4 total, 1 far).
UNHAPPY_EXTRA_PLANTS: list = [
    # Admission date BEFORE the date of birth (both Part 1).
    {"field_id": "date_of_admission",
     "event": "plant",
     "planted_say": "My date of admission was June twentieth, nineteen eighty.",
     "conflict_group": ["date_of_birth", "date_of_admission"],
     "correct_say": "Sorry, it was June twentieth, twenty fifteen.",
     "expected_after": "06/20/2015"},
    # City/state mismatch on the mailing address.
    {"field_id": "mail_city",
     "event": "plant",
     "planted_say": "My mailing city is Seattle.",
     "conflict_group": ["mail_city", "mail_state"],
     "correct_say": "Sorry, my city is Houston.",
     "expected_after": "Houston"},
]

# E4 reactivity micro-suite: short runs (the first `questions` steps of the
# full plan) ending in ONE seam event each -- clean per-seam distributions.
REACTIVITY_SUITE: list = [
    {"name": "nav-by-name", "questions": 16, "event": {
        "event": "navigate_back",
        "say": "Go back to my mailing city please.",
        "target_field_id": "mail_city",
        "correction_say": "It is Houston, that is correct.",
        "expected_after": None}},
    {"name": "nav-change-value", "questions": 16, "event": {
        "event": "navigate_back",
        "say": "I need to fix my apartment number, can we go back to it?",
        "target_field_id": "mail_unit_number",
        "correction_say": "It is apartment twelve A.",
        "expected_after": "12A"}},
    {"name": "nav-vague-address", "questions": 16, "event": {
        "event": "navigate_back",
        "say": "Can we go back to my address? I want to double check the street.",
        "target_field_id": "mail_street",
        "correction_say": "Yes, four two zero zero Westheimer Road is right.",
        "expected_after": None}},
    {"name": "nav-first-field", "questions": 16, "event": {
        "event": "navigate_back",
        "say": "Go back to the very first question, the alien number.",
        "target_field_id": "a_number",
        "correction_say": "Yes, A one two three four five six seven eight nine is correct.",
        "expected_after": None}},
    {"name": "recall-value", "questions": 16, "event": {
        "event": "recall",
        "say": "What did I say my alien registration number was?",
        "expect_field_ids": ["a_number"],
        "expect_contains": "123456789"}},
    {"name": "recall-empty", "questions": 16, "event": {
        "event": "recall",
        "say": "Did I give an in care of name for my mailing address?",
        "expect_field_ids": ["mail_in_care_of"],
        "expect_contains": None}},
    {"name": "recall-option", "questions": 16, "event": {
        "event": "recall",
        "say": "Remind me, did I say my name has changed since my card was issued?",
        "expect_field_ids": ["name_changed"],
        "expect_contains": "no"}},
    {"name": "recall-progress", "questions": 16, "event": {
        "event": "recall",
        "say": "How much of the form have we finished so far?",
        "expect_field_ids": [],
        "expect_contains": None}},
]


def weave_events(questions: list, events: list, expected: dict,
                 mix_unhappy_every: int = 0) -> tuple:
    """Interleave the event script into the question plan.

    Returns (steps, expected2, planted_groups):
      - steps: the driver's step list (question dicts, some flagged, plus
        standalone event dicts inserted after their anchor question);
      - expected2: the expected-canon table with plant/skip/navigate
        overrides applied;
      - planted_groups: [set(field_ids), ...] for the validator P/R scorer.

    mix_unhappy_every=N flags every Nth un-flagged question step as
    path="unhappy" (the E2 80/20 mix at N=5). 0 disables.
    """
    expected2 = dict(expected)
    by_after: dict = {}
    by_field: dict = {}
    planted_groups: list = []

    for ev in events:
        kind = ev.get("event")
        if kind in ("recall", "navigate_back") and "after_field_id" in ev:
            by_after.setdefault(ev["after_field_id"], []).append(ev)
        elif kind in ("skip", "plant"):
            by_field[ev["field_id"]] = ev
        else:
            raise SystemExit(f"unplaceable event (no anchor): {ev}")

    known_fids = {q["field_id"] for q in questions}
    for anchor in list(by_after) + list(by_field):
        if anchor not in known_fids:
            raise SystemExit(f"event anchor {anchor!r} is not in the plan")

    steps: list = []
    unflagged_count = 0
    for q in questions:
        fid = q["field_id"]
        step = dict(q)
        ev = by_field.get(fid)
        if ev and ev["event"] == "skip":
            step["skip"] = True
            step["skip_say"] = ev["say"]
            expected2[fid] = ""
        elif ev and ev["event"] == "plant":
            step["plant"] = {
                "conflict_group": list(ev["conflict_group"]),
                "correct_say": ev["correct_say"],
                "expected_after": ev["expected_after"],
            }
            step["planted_say"] = ev["planted_say"]
            expected2[fid] = ev["expected_after"]
            planted_groups.append(set(ev["conflict_group"]))
        elif mix_unhappy_every:
            unflagged_count += 1
            if unflagged_count % mix_unhappy_every == 0:
                step["path"] = "unhappy"
        steps.append(step)
        for after_ev in by_after.get(fid, []):
            ev2 = dict(after_ev)
            ev2.pop("after_field_id", None)
            steps.append(ev2)
            if ev2["event"] == "navigate_back" and ev2.get("expected_after") is not None:
                expected2[ev2["target_field_id"]] = ev2["expected_after"]
    return steps, expected2, planted_groups


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def percentile(xs: list, p: float):
    """Nearest-rank percentile; None on empty input."""
    vals = sorted(x for x in xs if x is not None)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, int(round((p / 100.0) * (len(vals) - 1)))))
    return vals[k]


def latency_summary(xs: list) -> dict:
    return {"n": len([x for x in xs if x is not None]),
            "p50": percentile(xs, 50), "p90": percentile(xs, 90),
            "p95": percentile(xs, 95), "max": percentile(xs, 100)}


def score_validator_pr(planted_groups: list, flagged_groups: list) -> dict:
    """Precision/recall of the validator against the planted contradictions.

    planted_groups: [set(field_ids), ...] from weave_events.
    flagged_groups: [set(field_ids), ...] -- every distinct conflict group the
    run's validation_result envelopes carried (dedupe by frozenset upstream).

    recall    = planted groups covered by some flagged group (g1b_scoring's
                prefix-tolerant containment) / planted.
    precision = flagged groups attributable to a plant / total flagged.
                "Attributable" is INTERSECTION with a planted group's fields,
                not exact coverage: a plant creates knock-on genuine conflicts
                (the planted Seattle ZIP also contradicts the physical-address
                ZIP), and those flags are correct behavior, not false
                positives. A flagged group touching NO planted field on a
                zero-contradiction persona is a genuine false positive (the
                annoyance metric).
    """
    planted = [set(map(str, g)) for g in planted_groups]
    flagged = [set(map(str, g)) for g in flagged_groups]

    def _covered(exp: set, flg: set) -> bool:
        return g1b_scoring._group_covered(exp, flg)

    def _touches(flg: set, exp: set) -> bool:
        return any(g1b_scoring.ids_match(a, b) for a in flg for b in exp)

    recalled = [g for g in planted if any(_covered(g, f) for f in flagged)]
    attributable = [f for f in flagged if any(_touches(f, g) for g in planted)]
    false_pos = [sorted(f) for f in flagged
                 if not any(_touches(f, g) for g in planted)]
    return {
        "planted": len(planted),
        "recalled": len(recalled),
        "recall": round(len(recalled) / len(planted), 4) if planted else None,
        "flagged_groups": len(flagged),
        "plant_attributable": len(attributable),
        "precision": (round(len(attributable) / len(flagged), 4)
                      if flagged else None),
        "false_positive_groups": false_pos,
        "missed_groups": [sorted(g) for g in planted if g not in recalled],
    }


_WORD_DIGITS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


def _canon(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    toks = [_WORD_DIGITS.get(t, t) for t in re.split(r"\s+", s) if t]
    return re.sub(r"[^a-z0-9]", "", "".join(toks))


def _try_date_norm(s: str):
    """Parse common date renderings to MM/DD/YYYY, else None."""
    s = str(s).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y", "%B %d, %Y",
                "%b %d, %Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return None


def _edit_distance(a: str, b: str) -> int:
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j, cb in enumerate(b, 1):
        cur = [j]
        for i, ca in enumerate(a, 1):
            cur.append(min(prev[i] + 1, cur[i - 1] + 1,
                           prev[i - 1] + (ca != cb)))
        prev = cur
    return prev[len(a)]


def classify_fill_failures(fill_detail: list, expected: dict) -> dict:
    """Classify each WRONG fill (fill_accuracy detail rows with ok=False) into
    a failure mode -- each mode has a different fix, so the aggregate is a
    diagnosis, not just a score:
      missing        nothing written (None/'') where a value was expected
      format         same data, different rendering (date formats normalize
                     to the same MM/DD/YYYY)
      transcription  canon edit-distance <= 2 of expected (Vasquez->Vazquez)
      wrong-field    the written value canon-matches ANOTHER field's expected
                     (a misrouted fill)
      mismatch       everything else (wrong data)
      spurious       a value written where the expected canon is EMPTY
    """
    modes: dict = {"missing": [], "format": [], "transcription": [],
                   "wrong-field": [], "mismatch": [], "spurious": []}
    exp_canon_by_fid = {}
    for fid, exp in expected.items():
        vals = exp if isinstance(exp, (list, tuple)) else [exp]
        exp_canon_by_fid[fid] = {_canon(v) for v in vals if v != ""}

    for row in fill_detail:
        if row.get("ok"):
            continue
        fid = row.get("field_id")
        written = row.get("written")
        exp = row.get("expected")
        exp_list = exp if isinstance(exp, (list, tuple)) else [exp]
        if exp == "" or exp == [""]:
            modes["spurious"].append(fid)
            continue
        if written in (None, ""):
            modes["missing"].append(fid)
            continue
        wd = _try_date_norm(written)
        if wd is not None and any(_try_date_norm(e) == wd for e in exp_list
                                  if e is not None):
            modes["format"].append(fid)
            continue
        wc = _canon(written)
        if any(_edit_distance(wc, _canon(e)) <= 2 for e in exp_list
               if e not in (None, "")):
            modes["transcription"].append(fid)
            continue
        if any(wc in canons and ofid != fid
               for ofid, canons in exp_canon_by_fid.items() if wc):
            modes["wrong-field"].append(fid)
            continue
        modes["mismatch"].append(fid)
    return {k: v for k, v in modes.items()}
