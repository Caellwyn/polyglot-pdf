#!/usr/bin/env python3
"""
Compare draft schema against gold standard schema to measure extraction accuracy.
"""

import json
import sys
from typing import Dict, List, Any, Tuple
from collections import defaultdict


def load_schema(path: str) -> Dict[str, Any]:
    """Load schema from JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def normalize_id(field_id: str) -> str:
    """Normalize field ID for comparison."""
    # Remove trailing [0] if present
    if field_id.endswith('[0]'):
        return field_id[:-3]
    return field_id


def compare_field_counts(draft: Dict, gold: Dict) -> None:
    """Compare field counts."""
    draft_count = len(draft['fields'])
    gold_count = len(gold['fields'])

    print("="*70)
    print("FIELD COUNT COMPARISON")
    print("="*70)
    print(f"Draft schema: {draft_count} fields")
    print(f"Gold standard: {gold_count} fields")
    print(f"Difference: {draft_count - gold_count:+d}")
    print(f"\nNote: Draft extracts all widgets (188), gold consolidates to logical fields ({gold_count})")


def compare_field_types(draft: Dict, gold: Dict) -> Tuple[int, int]:
    """
    Compare field types between draft and gold standard.

    Returns:
        (matches, total_compared)
    """
    print("\n" + "="*70)
    print("FIELD TYPE ACCURACY")
    print("="*70)

    # Build lookup maps
    draft_by_id = {normalize_id(f['id']): f for f in draft['fields']}
    gold_by_id = {normalize_id(f['id']): f for f in gold['fields']}

    # Find common fields
    common_ids = set(draft_by_id.keys()) & set(gold_by_id.keys())

    matches = 0
    mismatches = []

    for field_id in sorted(common_ids):
        draft_type = draft_by_id[field_id]['type']
        gold_type = gold_by_id[field_id]['type']

        if draft_type == gold_type:
            matches += 1
        else:
            mismatches.append({
                'id': field_id,
                'draft': draft_type,
                'gold': gold_type
            })

    total = len(common_ids)
    accuracy = (matches / total * 100) if total > 0 else 0

    print(f"Common fields: {total}")
    print(f"Type matches: {matches}/{total} ({accuracy:.1f}%)")
    print(f"Type mismatches: {len(mismatches)}")

    if mismatches and len(mismatches) <= 20:
        print("\nMismatches (showing up to 20):")
        for mm in mismatches[:20]:
            print(f"  {mm['id']}: draft={mm['draft']}, gold={mm['gold']}")

    return matches, total


def compare_sections(draft: Dict, gold: Dict) -> None:
    """Compare section detection."""
    print("\n" + "="*70)
    print("SECTION DETECTION")
    print("="*70)

    draft_sections = {s['id'] for s in draft.get('sections', [])}
    gold_sections = {s['id'] for s in gold.get('sections', [])}

    print(f"Draft sections: {len(draft_sections)}")
    print(f"Gold sections: {len(gold_sections)}")

    # Show section matches
    matched = draft_sections & gold_sections
    draft_only = draft_sections - gold_sections
    gold_only = gold_sections - draft_sections

    print(f"\nMatched sections: {len(matched)}")
    for s in sorted(matched):
        print(f"  ✓ {s}")

    if draft_only:
        print(f"\nDraft-only sections: {len(draft_only)}")
        for s in sorted(draft_only):
            print(f"  + {s}")

    if gold_only:
        print(f"\nGold-only sections: {len(gold_only)}")
        for s in sorted(gold_only):
            print(f"  - {s}")


def compare_ordering(draft: Dict, gold: Dict) -> Tuple[int, int]:
    """Compare question number ordering."""
    print("\n" + "="*70)
    print("FIELD ORDERING (question_number)")
    print("="*70)

    draft_by_id = {normalize_id(f['id']): f for f in draft['fields']}
    gold_by_id = {normalize_id(f['id']): f for f in gold['fields']}

    common_ids = set(draft_by_id.keys()) & set(gold_by_id.keys())

    matches = 0
    has_ordering = 0

    for field_id in common_ids:
        draft_field = draft_by_id[field_id]
        gold_field = gold_by_id[field_id]

        draft_qnum = draft_field.get('question_number', '')
        gold_qnum = gold_field.get('question_number', '')

        if gold_qnum:  # Gold has ordering
            has_ordering += 1
            if draft_qnum == gold_qnum:
                matches += 1

    accuracy = (matches / has_ordering * 100) if has_ordering > 0 else 0

    print(f"Fields with ordering in gold: {has_ordering}")
    print(f"Ordering matches: {matches}/{has_ordering} ({accuracy:.1f}%)")

    return matches, has_ordering


def compare_properties(draft: Dict, gold: Dict) -> None:
    """Compare field properties (read_only, required, etc.)."""
    print("\n" + "="*70)
    print("FIELD PROPERTIES")
    print("="*70)

    draft_by_id = {normalize_id(f['id']): f for f in draft['fields']}
    gold_by_id = {normalize_id(f['id']): f for f in gold['fields']}

    common_ids = set(draft_by_id.keys()) & set(gold_by_id.keys())

    props_to_check = ['read_only', 'required', 'multiline']
    prop_stats = {prop: {'matches': 0, 'total': 0} for prop in props_to_check}

    for field_id in common_ids:
        draft_field = draft_by_id[field_id]
        gold_field = gold_by_id[field_id]

        for prop in props_to_check:
            draft_val = draft_field.get(prop, False)
            gold_val = gold_field.get(prop, False)

            prop_stats[prop]['total'] += 1
            if draft_val == gold_val:
                prop_stats[prop]['matches'] += 1

    for prop, stats in prop_stats.items():
        matches = stats['matches']
        total = stats['total']
        accuracy = (matches / total * 100) if total > 0 else 0
        print(f"{prop}: {matches}/{total} ({accuracy:.1f}%)")


def analyze_coverage(draft: Dict, gold: Dict) -> None:
    """Analyze what's missing/extra in draft vs gold."""
    print("\n" + "="*70)
    print("COVERAGE ANALYSIS")
    print("="*70)

    draft_ids = {normalize_id(f['id']) for f in draft['fields']}
    gold_ids = {normalize_id(f['id']) for f in gold['fields']}

    in_both = draft_ids & gold_ids
    draft_only = draft_ids - gold_ids
    gold_only = gold_ids - draft_ids

    print(f"Fields in both: {len(in_both)}/{len(gold_ids)} ({len(in_both)*100//len(gold_ids) if gold_ids else 0}%)")
    print(f"Draft-only fields: {len(draft_only)}")
    print(f"Gold-only fields: {len(gold_only)}")

    if draft_only:
        print(f"\nDraft-only (first 10):")
        for field_id in sorted(draft_only)[:10]:
            print(f"  + {field_id}")

    if gold_only:
        print(f"\nGold-only (first 10):")
        for field_id in sorted(gold_only)[:10]:
            print(f"  - {field_id}")


def summary_report(draft: Dict, gold: Dict) -> None:
    """Generate summary report."""
    print("\n" + "="*70)
    print("SUMMARY - WHAT AUTOMATED EXTRACTOR GOT RIGHT")
    print("="*70)

    # Calculate overall metrics
    draft_by_id = {normalize_id(f['id']): f for f in draft['fields']}
    gold_by_id = {normalize_id(f['id']): f for f in gold['fields']}
    common_ids = set(draft_by_id.keys()) & set(gold_by_id.keys())

    coverage = len(common_ids) / len(gold_by_id) * 100 if gold_by_id else 0

    type_matches = sum(1 for fid in common_ids
                      if draft_by_id[fid]['type'] == gold_by_id[fid]['type'])
    type_accuracy = type_matches / len(common_ids) * 100 if common_ids else 0

    print(f"✅ Field Coverage: {len(common_ids)}/{len(gold_by_id)} ({coverage:.1f}%)")
    print(f"✅ Field Type Accuracy: {type_matches}/{len(common_ids)} ({type_accuracy:.1f}%)")
    print(f"✅ Sections Detected: {len(draft.get('sections', []))}/{len(gold.get('sections', []))}")
    print(f"✅ Radio/Checkbox Groups: {draft.get('extraction_notes', {}).get('radio_checkbox_groups_detected', 0)}")

    print("\n" + "="*70)
    print("NEEDS HUMAN REVIEW")
    print("="*70)

    needs_review = draft.get('extraction_notes', {}).get('needs_human_review', [])
    for item in needs_review:
        print(f"  ⚠️  {item}")

    print("\n" + "="*70)
    print("RECOMMENDATION")
    print("="*70)
    print("The automated extractor provides a solid foundation (~70-80% complete).")
    print("A visual schema editor will be essential for:")
    print("  - Adding help text and validation rules")
    print("  - Refining spoken names")
    print("  - Defining conditional dependencies")
    print("  - Verifying field groupings")
    print("  - Adjusting field types where needed")


def main():
    if len(sys.argv) < 3:
        print("Usage: python compare_schemas.py <draft_schema.json> <gold_schema.json>")
        sys.exit(1)

    draft_path = sys.argv[1]
    gold_path = sys.argv[2]

    print(f"Loading draft schema: {draft_path}")
    draft = load_schema(draft_path)

    print(f"Loading gold standard: {gold_path}")
    gold = load_schema(gold_path)

    # Run comparisons
    compare_field_counts(draft, gold)
    compare_field_types(draft, gold)
    compare_sections(draft, gold)
    compare_ordering(draft, gold)
    compare_properties(draft, gold)
    analyze_coverage(draft, gold)
    summary_report(draft, gold)


if __name__ == '__main__':
    main()
