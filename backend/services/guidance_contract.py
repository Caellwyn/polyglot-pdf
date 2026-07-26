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

Size bounds (sprint-16 plan + the wsao.2 measurement):
  - instructions: soft <= INSTRUCTIONS_SOFT_CHARS (speakable ask-tail), hard
    INSTRUCTIONS_HARD_CHARS (lint WARNING above it);
  - details: DETAILS_OVERSIZE_WORDS lint WARNING. NOTE (wsao.2 finding): the
    live session's ctu8-derived compression window imposes a HARD form-
    dependent token budget on inline details (w7: between 1,717 and 3,366
    tokens -- 3,366 breached the ~6,400-token assembled budget and Vertex
    closed 1007 at session assemble). The oversize POLICY (bake-time cap vs
    bigger window vs secretary-mediated delivery) is a reserved maintainer
    decision; until it lands, the lint bound stays WARNING-level and the
    engine must consult scripts/spikes/wsao2_inline_details_findings.md.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

INSTRUCTIONS_SOFT_CHARS = 280
INSTRUCTIONS_HARD_CHARS = 500
DETAILS_OVERSIZE_WORDS = 3000
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
    through. See the module docstring before changing anything here."""
    if not text:
        return ""
    for src, dst in _PUNCT_FOLD.items():
        text = text.replace(src, dst)
    # join line-break hyphenation BEFORE whitespace collapse ("with-\nholding")
    text = re.sub(r"-\s*\n\s*", "", text)
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
- Size: watch the per-form inline token budget (wsao.2: the live session's
  compression window HARD-caps what can ride inline; w7's budget lies between
  1,717 and 3,366 tokens).
"""
