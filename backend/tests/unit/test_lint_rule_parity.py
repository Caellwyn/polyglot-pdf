"""Local and hosted lint must surface the SAME rules (bd polyglot-pdf-cpiw.3).

The bug this guards: local mode ran a lighter CLIENT-SIDE ruleset that emitted
`rule: ''` for every finding. The editor's guidance-staleness gate matches on a
rule ID, so it never fired -- a field whose name changed after its guidance was
written kept reading green, with nothing on screen to say a check had been
skipped. Two implementations of "lint" silently disagreed.

The fix routes local mode at the same Python linter, so rule IDs are now
identical BY CONSTRUCTION. What can still rot is the UI layer: a rule the
backend emits that the panel has no label for, or a label for a rule that no
longer exists. Both are silent -- the first renders a terse internal id at a
reviewer, the second is dead code that hides a rename.

So this test reads the two sources and compares them. It is deliberately a
BACKEND test: the backend owns the rule vocabulary, and a new rule added here
should fail here rather than waiting for someone to run the editor suite.

ASCII only.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
# RULE_LABELS moved from ValidationPanel.tsx to the shared lintFindings module
# when the warnings pane dissolved into embedded findings (sprint-18 C1, bd
# polyglot-pdf-o7y9) -- the label vocabulary is now consumed by the FieldEditor
# anchors and the FieldList Form row, not a pane.
_PANEL_TSX = _REPO / "schema-editor" / "src" / "utils" / "lintFindings.ts"

_LINT_PY = _REPO / "backend" / "services" / "schema_lint.py"

# Rules the panel deliberately does not label, with the reason. Keep this SMALL
# and justified -- it is the escape hatch, not the norm.
_UNLABELLED_OK: dict[str, str] = {}

# A rule id reaches a finding two ways in schema_lint, and BOTH are scanned:
#   1. emitted inline           LintFinding(SEVERITY_X, "<rule>", ...)
#   2. re-emitted from a bake   the flag-taxonomy frozensets, whose members
#                               become the finding's rule verbatim
# Deliberately NOT scanned: translation_lint's CHECK_* constants
# (mask-broken, dnt-violated, wrong-script, ...). Those are the `check`
# SUB-KIND carried INSIDE a finding whose rule is always
# translation-mechanical -- they never appear as a rule, so the panel is right
# not to label them. Verified at translation_lint.py:694/728, where every
# emission passes rule=RULE_MECHANICAL.
_INLINE_RE = re.compile(r'SEVERITY_(?:ERROR|WARNING),\s*"([a-z0-9-]+)"')
_TAXONOMY_RE = re.compile(
    r"frozenset\(\{([^}]*)\}\)", re.DOTALL)
_MEMBER_RE = re.compile(r'"([a-z][a-z0-9]*(?:-[a-z0-9]+)+)"')


_GUIDANCE_PY = _REPO / "backend" / "services" / "guidance_contract.py"


def _backend_rule_ids() -> set[str]:
    """Every rule id the backend can put on a finding."""
    src = _LINT_PY.read_text(encoding="utf-8")
    ids = set(_INLINE_RE.findall(src))
    for block in _TAXONOMY_RE.findall(src):
        ids |= set(_MEMBER_RE.findall(block))
    # GUIDANCE_FLAG_RULES lives in guidance_contract but schema_lint re-emits
    # its members as findings verbatim, so they reach the panel like any rule.
    guidance = _GUIDANCE_PY.read_text(encoding="utf-8")
    block = re.search(r"GUIDANCE_FLAG_RULES = frozenset\(\{(.*?)\}\)",
                      guidance, re.DOTALL)
    if block:
        ids |= set(_MEMBER_RE.findall(block.group(1)))
    return ids


def _panel_labelled_rule_ids() -> set[str]:
    """The rule ids RULE_LABELS in lintFindings.ts has a label for."""
    src = _PANEL_TSX.read_text(encoding="utf-8")
    block = re.search(
        r"const RULE_LABELS: Record<string, string> = \{(.*?)\n\};",
        src, re.DOTALL)
    assert block, "RULE_LABELS not found in lintFindings.ts"
    return set(re.findall(r"'([a-z0-9-]+)':", block.group(1)))


def test_the_panel_labels_every_rule_the_backend_emits():
    backend = _backend_rule_ids()
    panel = _panel_labelled_rule_ids()
    assert backend, "no rule ids parsed from schema_lint.py -- test is vacuous"

    unlabelled = sorted(backend - panel - set(_UNLABELLED_OK))
    assert unlabelled == [], (
        "these lint rules have no human-readable label in lintFindings.ts, "
        f"so a reviewer sees the raw internal id: {unlabelled}. Add them to "
        "RULE_LABELS (or to _UNLABELLED_OK here, with a reason)."
    )


def test_the_panel_has_no_labels_for_rules_that_no_longer_exist():
    backend = _backend_rule_ids()
    panel = _panel_labelled_rule_ids()
    stale = sorted(panel - backend)
    assert stale == [], (
        "lintFindings.ts labels rule ids the backend no longer emits: "
        f"{stale}. A renamed rule leaves its old label behind and the NEW id "
        "renders unlabelled, which is the silent-drift this pins."
    )


def _panel_remedy_rule_ids() -> set[str]:
    """The rule ids RULE_REMEDIES in lintFindings.ts has a remedy for."""
    src = _PANEL_TSX.read_text(encoding="utf-8")
    block = re.search(
        r"export const RULE_REMEDIES: Record<string, string> = \{(.*?)\n\};",
        src, re.DOTALL)
    assert block, "RULE_REMEDIES not found in lintFindings.ts"
    return set(re.findall(r"'([a-z0-9-]+)':", block.group(1)))


def test_the_remedy_map_tracks_the_label_map():
    """RULE_REMEDIES (bd xfdb) is forward-staging for the embedded-findings
    UI (sprint-18 C1): every labelled rule carries one imperative remedy
    sentence. Without this pin, a new rule ships with a label but a blank
    remedy line the moment C1 wires the map in -- the same silent-drift
    class the label tests above exist to catch, one map over (Opus round 2,
    bd xfdb)."""
    labels = _panel_labelled_rule_ids()
    remedies = _panel_remedy_rule_ids()
    missing = sorted(labels - remedies)
    assert missing == [], (
        "these rules have a RULE_LABELS entry but no RULE_REMEDIES sentence: "
        f"{missing}. Add the remedy (what should the reviewer DO?)."
    )
    stale = sorted(remedies - labels)
    assert stale == [], (
        f"RULE_REMEDIES names rules RULE_LABELS does not: {stale}."
    )


def test_the_guidance_staleness_rule_id_matches_on_both_sides():
    """The specific id the ack gate keys on (bd anim / bd cpiw).

    A rename on either side silently disables the gate -- staleFieldIds()
    would match nothing and every drifted field would read green again, the
    exact bug this bead was filed for.
    """
    rule = "guidance-identity-stale"
    assert rule in _backend_rule_ids()
    staleness_ts = (_REPO / "schema-editor" / "src" / "utils"
                    / "guidanceStaleness.ts").read_text(encoding="utf-8")
    assert f"GUIDANCE_STALE_RULE = '{rule}'" in staleness_ts, (
        "the editor's GUIDANCE_STALE_RULE no longer matches the backend's "
        f"rule id {rule!r} -- the acknowledgment gate is now inert"
    )
