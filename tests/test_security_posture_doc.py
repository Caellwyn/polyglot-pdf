"""docs/standards/security-posture.md's inventory table names EXACTLY the
stores scripts/audit/inventory_stores.py iterates (sprint 23 epic criterion
1, bd polyglot-pdf-vzrbc).

The doc side is the STORE cell only -- the first backticked identifier of
each row's first cell (never the prose columns: a store name-dropped in the
"Guard" or "Readers" cell must not count, bd abn4o). The script side is
derived from the script's SOURCE, not hand-listed: the PINNED_ALLOWLISTS
keys minus the four subcollection allowlist keys, plus the four
subcollection report names, plus the bucket, plus every default BigQuery
view. A row with no backticked store is a store the script cannot read and
must name the check that covers it instead.

Mutations (each RED): delete the `alerts` row; add a row for a store the
script does not iterate (`bigquery:made_up`); drop the `infra_posture.sh`
pointer from the Firebase Auth row.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "standards" / "security-posture.md"
SCRIPT = REPO_ROOT / "scripts" / "audit" / "inventory_stores.py"

# The checks a non-scripted store may point at instead of the inventory.
_OTHER_CHECKS = (
    "infra_posture.sh", "log_pii_sweep.py", "detect-secrets", "design note",
    "test_no_pii_logging.py",
)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start: nxt if nxt != -1 else len(text)]


def _table_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= {"-", " "} or cells[0] == "Store":
            continue
        rows.append(cells)
    return rows


def doc_rows() -> list[list[str]]:
    rows = _table_rows(_section(DOC.read_text(encoding="utf-8"), "## Data inventory"))
    assert len(rows) >= 20, "the inventory table is suspiciously short: %d rows" % len(rows)
    return rows


def doc_scripted_stores() -> set[str]:
    out = set()
    for cells in doc_rows():
        m = re.match(r"^`([^`]+)`", cells[0])
        if m:
            out.add(m.group(1))
    return out


def script_stores() -> set[str]:
    src = SCRIPT.read_text(encoding="utf-8")
    block = src[src.index("PINNED_ALLOWLISTS"):]
    block = block[: block.index("\n}\n") + 3]
    keys = set(re.findall(r'^    "([a-z_]+)":', block, flags=re.M))
    assert keys, "no PINNED_ALLOWLISTS keys parsed"
    subs = re.findall(
        r'\("([a-z_/*]+)", "([a-z_]+)", "([a-z_]+)", "([a-z_]+)"\)', src)
    assert len(subs) == 4, subs
    report_names = {s[0] for s in subs}
    allowlist_keys = {s[3] for s in subs}
    bq_block = src[src.index('"--bq-tables"'):]
    bq_block = bq_block[: bq_block.index("]") + 1]
    views = re.findall(r'"([a-z_]+)"', bq_block[bq_block.index("default="):])
    assert len(views) >= 3, views
    return (keys - allowlist_keys) | report_names | {"bucket"} | {"bigquery:" + v for v in views}


def test_the_doc_and_the_script_iterate_the_same_stores():
    doc = doc_scripted_stores()
    script = script_stores()
    assert doc == script, (
        "doc-only: %s; script-only: %s" % (sorted(doc - script), sorted(script - doc)))


def test_every_unscripted_store_names_the_check_that_covers_it():
    for cells in doc_rows():
        if re.match(r"^`([^`]+)`", cells[0]):
            continue
        row = " | ".join(cells)
        assert any(c in row for c in _OTHER_CHECKS), (
            "unscripted store row names no covering check: %s" % cells[0][:60])


def test_every_row_carries_all_six_columns():
    for cells in doc_rows():
        assert len(cells) == 6, (cells[0][:60], len(cells))
        assert all(cells), cells[0][:60]
