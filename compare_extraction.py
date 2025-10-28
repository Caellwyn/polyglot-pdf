#!/usr/bin/env python3
"""
Compare extracted schema with ground truth schema.
Shows differences in field counts, table detection, etc.
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

def load_schema(path: str) -> Dict[str, Any]:
    """Load a schema JSON file."""
    with open(path, 'r') as f:
        return json.load(f)

def analyze_fields(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze field structure in a schema."""
    fields = schema.get('fields', [])

    field_counts = {
        'total': len(fields),
        'by_type': defaultdict(int),
        'by_section': defaultdict(int),
        'tables': [],
        'radio_groups': [],
        'checkbox_groups': []
    }

    for field in fields:
        field_type = field.get('type')
        section_id = field.get('section_id')

        field_counts['by_type'][field_type] += 1
        field_counts['by_section'][section_id] += 1

        if field_type == 'table':
            table_info = {
                'id': field.get('id'),
                'section': section_id,
                'columns': len(field.get('columns', [])),
                'rows': field.get('multi_entry', {}).get('initial_rows', 0)
            }
            field_counts['tables'].append(table_info)
        elif field_type == 'radio':
            field_counts['radio_groups'].append({
                'id': field.get('id'),
                'section': section_id,
                'options': len(field.get('options', []))
            })
        elif field_type == 'checkbox' and field.get('options'):
            field_counts['checkbox_groups'].append({
                'id': field.get('id'),
                'section': section_id,
                'options': len(field.get('options', []))
            })

    return field_counts

def print_comparison(ground_truth_path: str, extracted_path: str):
    """Print detailed comparison between ground truth and extracted schemas."""

    print("=" * 80)
    print("SCHEMA COMPARISON REPORT")
    print("=" * 80)
    print()

    gt_schema = load_schema(ground_truth_path)
    ex_schema = load_schema(extracted_path)

    gt_analysis = analyze_fields(gt_schema)
    ex_analysis = analyze_fields(ex_schema)

    # Overall field counts
    print("OVERALL FIELD COUNTS")
    print("-" * 80)
    print(f"Ground Truth: {gt_analysis['total']} fields")
    print(f"Extracted:    {ex_analysis['total']} fields")
    print(f"Difference:   {ex_analysis['total'] - gt_analysis['total']:+d} fields")
    print()

    # Field types comparison
    print("FIELD TYPES")
    print("-" * 80)
    all_types = set(gt_analysis['by_type'].keys()) | set(ex_analysis['by_type'].keys())
    print(f"{'Type':<15} {'Ground Truth':>15} {'Extracted':>15} {'Diff':>10}")
    print("-" * 80)
    for field_type in sorted(all_types):
        gt_count = gt_analysis['by_type'][field_type]
        ex_count = ex_analysis['by_type'][field_type]
        diff = ex_count - gt_count
        print(f"{field_type:<15} {gt_count:>15} {ex_count:>15} {diff:>10}")
    print()

    # Section-level comparison
    print("FIELDS PER SECTION")
    print("-" * 80)
    all_sections = set(gt_analysis['by_section'].keys()) | set(ex_analysis['by_section'].keys())
    print(f"{'Section':<30} {'Ground Truth':>15} {'Extracted':>15} {'Diff':>10}")
    print("-" * 80)
    for section_id in sorted(all_sections):
        gt_count = gt_analysis['by_section'][section_id]
        ex_count = ex_analysis['by_section'][section_id]
        diff = ex_count - gt_count
        print(f"{section_id:<30} {gt_count:>15} {ex_count:>15} {diff:>10}")
    print()

    # Table detection comparison
    print("TABLE DETECTION")
    print("-" * 80)
    print(f"Ground Truth: {len(gt_analysis['tables'])} tables")
    print(f"Extracted:    {len(ex_analysis['tables'])} tables")
    print()

    print("Ground Truth Tables:")
    for table in gt_analysis['tables']:
        print(f"  - {table['id']:<40} {table['columns']:>2} cols × {table['rows']:>2} rows")
    print()

    print("Extracted Tables:")
    for table in ex_analysis['tables']:
        print(f"  - {table['id']:<40} {table['columns']:>2} cols × {table['rows']:>2} rows")
    print()

    # Radio groups
    print("RADIO GROUPS")
    print("-" * 80)
    print(f"Ground Truth: {len(gt_analysis['radio_groups'])} groups")
    print(f"Extracted:    {len(ex_analysis['radio_groups'])} groups")
    print()

if __name__ == "__main__":
    ground_truth = "/home/user/polyglot-pdf/pdf_schema_extractor/test_schemas/test_pdfs/i589_schema.json"
    extracted = "/home/user/polyglot-pdf/pdf_schema_extractor/test_schemas/extracted_schema.json"

    print_comparison(ground_truth, extracted)
