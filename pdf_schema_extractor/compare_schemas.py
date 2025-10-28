"""
Compare extracted schema with expected schema and generate a report.
"""

import json
from pathlib import Path
from collections import defaultdict

def load_json(filepath):
    """Load a JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def compare_schemas(extracted, expected):
    """Compare two schemas and return differences."""
    differences = {
        'metadata': [],
        'parts': [],
        'sections': [],
        'supplements': [],
        'fields': [],
        'summary': {}
    }
    
    # Compare metadata
    if extracted.get('form_metadata') != expected.get('form_metadata'):
        differences['metadata'].append({
            'issue': 'Metadata mismatch',
            'extracted': extracted.get('form_metadata'),
            'expected': expected.get('form_metadata')
        })
    
    # Compare parts
    extracted_parts = extracted.get('parts', [])
    expected_parts = expected.get('parts', [])
    
    differences['summary']['parts_count'] = {
        'extracted': len(extracted_parts),
        'expected': len(expected_parts)
    }
    
    if len(extracted_parts) != len(expected_parts):
        differences['parts'].append({
            'issue': 'Different number of parts',
            'extracted_count': len(extracted_parts),
            'expected_count': len(expected_parts)
        })
    
    # Compare sections
    extracted_sections = {s['id']: s for s in extracted.get('sections', [])}
    expected_sections = {s['id']: s for s in expected.get('sections', [])}
    
    differences['summary']['sections_count'] = {
        'extracted': len(extracted_sections),
        'expected': len(expected_sections)
    }
    
    # Check for missing or extra sections
    missing_sections = set(expected_sections.keys()) - set(extracted_sections.keys())
    extra_sections = set(extracted_sections.keys()) - set(expected_sections.keys())
    
    if missing_sections:
        differences['sections'].append({
            'issue': 'Missing sections',
            'section_ids': list(missing_sections)
        })
    
    if extra_sections:
        differences['sections'].append({
            'issue': 'Extra sections',
            'section_ids': list(extra_sections)
        })
    
    # Compare section details for matching sections
    for section_id in set(extracted_sections.keys()) & set(expected_sections.keys()):
        ext_sec = extracted_sections[section_id]
        exp_sec = expected_sections[section_id]
        
        if ext_sec.get('label') != exp_sec.get('label'):
            differences['sections'].append({
                'issue': 'Section label mismatch',
                'section_id': section_id,
                'extracted': ext_sec.get('label'),
                'expected': exp_sec.get('label')
            })
    
    # Compare supplements
    extracted_supplements = extracted.get('supplements', [])
    expected_supplements = expected.get('supplements', [])
    
    differences['summary']['supplements_count'] = {
        'extracted': len(extracted_supplements),
        'expected': len(expected_supplements)
    }
    
    # Compare fields
    extracted_fields = {f['id']: f for f in extracted.get('fields', [])}
    expected_fields = {f['id']: f for f in expected.get('fields', [])}
    
    differences['summary']['fields_count'] = {
        'extracted': len(extracted_fields),
        'expected': len(expected_fields)
    }
    
    # Check for missing or extra fields
    missing_fields = set(expected_fields.keys()) - set(extracted_fields.keys())
    extra_fields = set(extracted_fields.keys()) - set(expected_fields.keys())
    
    if missing_fields:
        differences['fields'].append({
            'issue': 'Missing fields',
            'count': len(missing_fields),
            'sample_ids': list(missing_fields)[:10]  # Show first 10
        })
    
    if extra_fields:
        differences['fields'].append({
            'issue': 'Extra fields',
            'count': len(extra_fields),
            'sample_ids': list(extra_fields)[:10]  # Show first 10
        })
    
    # Compare field attributes for matching fields
    field_attr_diffs = defaultdict(list)
    for field_id in list(set(extracted_fields.keys()) & set(expected_fields.keys()))[:20]:  # Sample first 20
        ext_field = extracted_fields[field_id]
        exp_field = expected_fields[field_id]
        
        # Check key attributes
        for attr in ['name', 'spoken_name', 'type', 'section_id', 'pdf_field_name']:
            if ext_field.get(attr) != exp_field.get(attr):
                field_attr_diffs[attr].append({
                    'field_id': field_id,
                    'extracted': ext_field.get(attr),
                    'expected': exp_field.get(attr)
                })
    
    if field_attr_diffs:
        differences['fields'].append({
            'issue': 'Field attribute mismatches',
            'details': dict(field_attr_diffs)
        })
    
    return differences

def generate_report(differences, output_path):
    """Generate a markdown report from differences."""
    lines = [
        "# PDF Schema Extraction Comparison Report",
        "",
        f"Generated: {Path(__file__).name}",
        "",
        "## Summary",
        "",
        "### Counts",
        ""
    ]
    
    # Add summary counts
    for category, counts in differences['summary'].items():
        lines.append(f"**{category}:**")
        lines.append(f"- Extracted: {counts['extracted']}")
        lines.append(f"- Expected: {counts['expected']}")
        lines.append(f"- Match: {'✓' if counts['extracted'] == counts['expected'] else '✗'}")
        lines.append("")
    
    # Metadata differences
    if differences['metadata']:
        lines.append("## Metadata Differences")
        lines.append("")
        for diff in differences['metadata']:
            lines.append(f"### {diff['issue']}")
            lines.append("")
            lines.append("**Extracted:**")
            lines.append(f"```json\n{json.dumps(diff['extracted'], indent=2)}\n```")
            lines.append("")
            lines.append("**Expected:**")
            lines.append(f"```json\n{json.dumps(diff['expected'], indent=2)}\n```")
            lines.append("")
    
    # Parts differences
    if differences['parts']:
        lines.append("## Parts Differences")
        lines.append("")
        for diff in differences['parts']:
            lines.append(f"- {diff['issue']}: Extracted {diff['extracted_count']}, Expected {diff['expected_count']}")
        lines.append("")
    
    # Sections differences
    if differences['sections']:
        lines.append("## Sections Differences")
        lines.append("")
        for diff in differences['sections']:
            lines.append(f"### {diff['issue']}")
            lines.append("")
            if 'section_ids' in diff:
                for sec_id in diff['section_ids']:
                    lines.append(f"- `{sec_id}`")
            else:
                lines.append(f"**Section:** `{diff.get('section_id')}`")
                lines.append(f"- Extracted: {diff.get('extracted')}")
                lines.append(f"- Expected: {diff.get('expected')}")
            lines.append("")
    
    # Fields differences
    if differences['fields']:
        lines.append("## Fields Differences")
        lines.append("")
        for diff in differences['fields']:
            lines.append(f"### {diff['issue']}")
            lines.append("")
            if 'count' in diff:
                lines.append(f"**Count:** {diff['count']}")
                lines.append("")
                lines.append("**Sample IDs:**")
                for fid in diff.get('sample_ids', []):
                    lines.append(f"- `{fid}`")
            elif 'details' in diff:
                for attr, items in diff['details'].items():
                    lines.append(f"#### Attribute: `{attr}`")
                    lines.append("")
                    for item in items[:5]:  # Show first 5
                        lines.append(f"**Field:** `{item['field_id']}`")
                        lines.append(f"- Extracted: `{item['extracted']}`")
                        lines.append(f"- Expected: `{item['expected']}`")
                        lines.append("")
            lines.append("")
    
    # Required Changes section
    lines.extend([
        "## Required Changes to Extractor",
        "",
        "Based on the differences above, the following changes are needed:",
        "",
        "### 1. Field ID Generation",
        "- **Issue:** Field IDs don't match expected format",
        "- **Current:** Using sanitized PDF field names (e.g., `form1__subform_PtAILine1_ANumber`)",
        "- **Expected:** Using semantic IDs (e.g., `part_a_i_a_number`)",
        "- **Fix:** Implement semantic field ID generation based on field labels and context",
        "",
        "### 2. Section IDs",
        "- **Issue:** Section IDs use generic numbering",
        "- **Current:** `section_1`, `section_2`, etc.",
        "- **Expected:** Semantic IDs like `part_a_i`, `part_a_ii`, etc.",
        "- **Fix:** Parse section labels to generate semantic section IDs",
        "",
        "### 3. Field Attributes",
        "- **Issue:** Missing or incorrect field attributes",
        "- **Missing:** `spoken_name`, `help`, `validation`, `options` details",
        "- **Fix:** Need to extract field tooltips, help text, and validation rules from PDF",
        "",
        "### 4. Form Metadata",
        "- **Issue:** Incomplete metadata extraction",
        "- **Missing:** `form_number`, `edition_date`, `expiration_date`, `omb_number`, `agency`",
        "- **Fix:** Extract these from PDF metadata or first page text",
        "",
        "### 5. Section Structure",
        "- **Issue:** Section hierarchy and page numbers",
        "- **Missing:** Proper `page_numbers` arrays, section nesting",
        "- **Fix:** Track all pages a section appears on, not just the first",
        "",
        "### 6. Field Types",
        "- **Issue:** Type inference may be incomplete",
        "- **Fix:** Verify all field types are correctly identified (text, checkbox, radio, select, date, tel, signature, textarea, table)",
        "",
        "### 7. Supplement Structure",
        "- **Issue:** Supplements may not have all required fields",
        "- **Missing:** `trigger_condition`, `page_number`, detailed `purpose`",
        "- **Fix:** Add these metadata fields to supplement extraction",
        "",
        "## Priority Actions",
        "",
        "1. **High Priority:**",
        "   - Fix field ID generation (semantic vs. PDF field names)",
        "   - Fix section ID generation",
        "   - Extract complete form metadata",
        "",
        "2. **Medium Priority:**",
        "   - Add field `spoken_name` extraction from tooltips",
        "   - Add `help` text extraction",
        "   - Improve validation rules extraction",
        "",
        "3. **Low Priority:**",
        "   - Add supplement trigger conditions",
        "   - Refine section page tracking",
        "   - Add field options for radio/select fields",
    ])
    
    # Write report
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"Report generated: {output_path}")

if __name__ == "__main__":
    base_path = Path(__file__).parent
    
    extracted_path = base_path / "test_schemas" / "extracted_schema.json"
    expected_path = base_path.parent / "example_pdfs" / "i-589" / "i589_schema.json"
    report_path = base_path / "test_schemas" / "comparison_report.md"
    
    print("Loading schemas...")
    extracted = load_json(extracted_path)
    expected = load_json(expected_path)
    
    print("Comparing schemas...")
    differences = compare_schemas(extracted, expected)
    
    print("Generating report...")
    generate_report(differences, report_path)
    
    print("\nComparison complete!")
    print(f"Fields: {differences['summary']['fields_count']['extracted']} extracted vs {differences['summary']['fields_count']['expected']} expected")
    print(f"Sections: {differences['summary']['sections_count']['extracted']} extracted vs {differences['summary']['sections_count']['expected']} expected")
