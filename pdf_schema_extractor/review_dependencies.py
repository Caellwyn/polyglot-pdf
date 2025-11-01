#!/usr/bin/env python3
"""
Dependency Review Tool - Interactive review and correction of Gemini-extracted dependencies.

This tool helps you:
1. Review dependencies extracted by Gemini
2. Identify missing dependencies (especially for read-only fields)
3. Correct incorrect triggers
4. Add missing dependencies
5. Export validated dependencies

Usage:
    python review_dependencies.py <schema.json> <dependencies.json> [output.json]
"""

import json
import sys
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class DependencyReviewer:
    """Interactive dependency review and correction tool."""

    def __init__(self, schema_path: str, dependencies_path: str):
        self.schema_path = schema_path
        self.dependencies_path = dependencies_path

        # Load schema
        with open(schema_path, 'r', encoding='utf-8') as f:
            self.schema = json.load(f)

        # Load dependencies
        with open(dependencies_path, 'r', encoding='utf-8') as f:
            self.dependencies = json.load(f)

        # Index fields
        self.fields_by_id = {f['id']: f for f in self.schema['fields']}

        # Index dependencies
        self.deps_by_field = {}
        for dep in self.dependencies.get('fields', []):
            field_id = dep['field_id']
            if field_id not in self.deps_by_field:
                self.deps_by_field[field_id] = []
            self.deps_by_field[field_id].append(dep)

    def analyze_coverage(self) -> Dict:
        """Analyze dependency coverage and identify issues."""
        readonly_fields = [f['id'] for f in self.schema['fields'] if f.get('read_only') == True]
        has_show_if = [d['field_id'] for d in self.dependencies['fields'] if d.get('show_if')]

        missing_deps = [f for f in readonly_fields if f not in has_show_if]
        has_deps = [f for f in readonly_fields if f in has_show_if]

        # Check for duplicate entries
        from collections import Counter
        field_counts = Counter([d['field_id'] for d in self.dependencies['fields']])
        duplicates = [(fid, count) for fid, count in field_counts.items() if count > 1]

        return {
            'readonly_total': len(readonly_fields),
            'readonly_with_deps': len(has_deps),
            'readonly_missing_deps': len(missing_deps),
            'missing_deps_list': missing_deps,
            'duplicates': duplicates
        }

    def print_summary(self):
        """Print summary of current dependency state."""
        analysis = self.analyze_coverage()

        print("=" * 70)
        print("DEPENDENCY REVIEW SUMMARY")
        print("=" * 70)
        print(f"Schema: {Path(self.schema_path).name}")
        print(f"Dependencies: {Path(self.dependencies_path).name}")
        print()

        print(f"Total fields: {len(self.schema['fields'])}")
        print(f"Read-only fields: {analysis['readonly_total']}")
        print(f"  [+] With dependencies: {analysis['readonly_with_deps']}")
        print(f"  [-] Missing dependencies: {analysis['readonly_missing_deps']}")

        if analysis['duplicates']:
            print(f"\n[!] Duplicate entries: {len(analysis['duplicates'])} fields")

        print()

    def show_field_details(self, field_id: str):
        """Show detailed information about a field."""
        field = self.fields_by_id.get(field_id)
        if not field:
            print(f"Field {field_id} not found in schema")
            return

        print(f"\nField: {field_id}")
        print(f"  Name: {field.get('name', 'N/A')}")
        print(f"  Type: {field.get('type', 'N/A')}")
        print(f"  Section: {field.get('section', 'N/A')}")
        print(f"  Read-only: {field.get('read_only', False)}")

        # Show current dependencies
        deps = self.deps_by_field.get(field_id, [])
        if deps:
            print(f"\n  Current dependencies ({len(deps)} entries):")
            for i, dep in enumerate(deps, 1):
                print(f"\n  Entry {i}:")
                if dep.get('show_if'):
                    si = dep['show_if']
                    print(f"    show_if:")
                    print(f"      field: {si['field']}")
                    print(f"      operator: {si['operator']}")
                    print(f"      value: {si['value']}")
                if dep.get('conditional_fields'):
                    print(f"    conditional_fields: {dep['conditional_fields']}")
                if dep.get('confidence'):
                    print(f"    confidence: {dep['confidence']}")
                if dep.get('needs_unlock'):
                    print(f"    needs_unlock: {dep['needs_unlock']}")
        else:
            print("  No dependencies found")

    def find_candidate_triggers(self, field_id: str, max_results: int = 5) -> List[Dict]:
        """Find potential trigger fields based on proximity and patterns."""
        field = self.fields_by_id[field_id]
        field_idx = self.schema['fields'].index(field)
        section = field.get('section', '')

        candidates = []

        for candidate in self.schema['fields']:
            if candidate['id'] == field_id:
                continue

            candidate_idx = self.schema['fields'].index(candidate)
            candidate_section = candidate.get('section', '')

            score = 0
            reasons = []

            # Same section
            if candidate_section == section:
                score += 20
                reasons.append("same section")

            # Proximity (prefer fields before this one)
            distance = abs(field_idx - candidate_idx)
            if distance <= 5:
                proximity_score = 15 - distance * 2
                score += proximity_score
                if candidate_idx < field_idx:
                    score += 5  # Bonus for coming before
                    reasons.append(f"nearby ({distance} fields before)")
                else:
                    reasons.append(f"nearby ({distance} fields after)")

            # Field type patterns
            if candidate['type'] in ['checkbox', 'radio']:
                score += 10
                reasons.append("checkbox/radio")

            # ID pattern matching
            # Example: p1_line7b_aptsteflrnumber might be triggered by p1_unit_type7b_unit
            field_prefix = field_id.split('_')[0:2]  # ['p1', 'line7b']
            cand_prefix = candidate['id'].split('_')[0:2]
            if field_prefix == cand_prefix or any(p in candidate['id'] for p in field_id.split('_')[:3]):
                score += 15
                reasons.append("similar ID pattern")

            # Unit type pattern for apt/ste/flr fields
            if 'aptsteflr' in field_id and 'unit_type' in candidate['id']:
                score += 30
                reasons.append("unit_type for apt/ste/flr")

            # Checkbox groups (same prefix with [X] suffix)
            if '[' in field_id and '[' in candidate['id']:
                field_base = field_id.split('[')[0]
                cand_base = candidate['id'].split('[')[0]
                if field_base == cand_base:
                    score += 25
                    reasons.append("same checkbox group")

            if score > 0:
                candidates.append({
                    'id': candidate['id'],
                    'name': candidate.get('name', ''),
                    'type': candidate.get('type', ''),
                    'score': score,
                    'reasons': ', '.join(reasons)
                })

        # Sort by score
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:max_results]

    def review_missing_dependencies(self, interactive: bool = True):
        """Review fields missing dependencies."""
        analysis = self.analyze_coverage()
        missing = analysis['missing_deps_list']

        if not missing:
            print("\n[+] All read-only fields have dependencies!")
            return

        print(f"\n{'='*70}")
        print(f"REVIEWING {len(missing)} READ-ONLY FIELDS WITHOUT DEPENDENCIES")
        print(f"{'='*70}\n")

        corrections = []

        for i, field_id in enumerate(missing, 1):
            field = self.fields_by_id[field_id]

            print(f"\n[{i}/{len(missing)}] Field: {field_id}")
            print(f"  Name: {field.get('name', 'N/A')[:60]}")
            print(f"  Section: {field.get('section', 'N/A')}")

            # Show candidates
            candidates = self.find_candidate_triggers(field_id)
            if candidates:
                print(f"\n  Suggested trigger fields:")
                for j, cand in enumerate(candidates, 1):
                    print(f"    {j}. {cand['id']} (score: {cand['score']})")
                    print(f"       Type: {cand['type']}, Reasons: {cand['reasons']}")
                    print(f"       Name: {cand['name'][:50]}")

            if not interactive:
                continue

            # Get user input
            print(f"\n  Options:")
            print(f"    1-{len(candidates)}: Select suggested trigger")
            print(f"    m: Manual entry")
            print(f"    s: Skip this field")
            print(f"    q: Quit and save")

            choice = input(f"\n  Choice: ").strip().lower()

            if choice == 'q':
                break
            elif choice == 's':
                continue
            elif choice == 'm':
                trigger_id = input("  Enter trigger field ID: ").strip()
                if trigger_id not in self.fields_by_id:
                    print(f"  [-] Field {trigger_id} not found in schema")
                    continue
            elif choice.isdigit() and 1 <= int(choice) <= len(candidates):
                trigger_id = candidates[int(choice) - 1]['id']
            else:
                print("  Invalid choice, skipping")
                continue

            # Get operator
            print(f"\n  Operators: equals, not_equals, is_checked, is_not_empty, in")
            operator = input(f"  Operator [equals]: ").strip() or "equals"

            # Get value
            trigger_field = self.fields_by_id[trigger_id]
            if trigger_field.get('type') in ['checkbox', 'radio'] and trigger_field.get('options'):
                print(f"\n  Available options:")
                for opt in trigger_field['options'][:5]:
                    if isinstance(opt, dict):
                        print(f"    - {opt.get('value', opt.get('label', ''))}")
                    else:
                        print(f"    - {opt}")

            value = input(f"  Trigger value: ").strip()

            # Get confidence
            confidence = input(f"  Confidence (high/medium/low) [high]: ").strip() or "high"

            # Create correction
            correction = {
                'field_id': field_id,
                'show_if': {
                    'field': trigger_id,
                    'operator': operator,
                    'value': value
                },
                'needs_unlock': True,
                'confidence': confidence
            }

            corrections.append(correction)
            print(f"  [+] Added dependency: {field_id} <- {trigger_id}")

        return corrections

    def save_corrections(self, corrections: List[Dict], output_path: str):
        """Apply corrections and save updated dependencies."""
        # Merge corrections with existing dependencies
        updated_deps = self.dependencies.copy()

        # Add new dependencies
        for correction in corrections:
            updated_deps['fields'].append(correction)

            # Add bidirectional link (conditional_fields)
            trigger_id = correction['show_if']['field']
            trigger_entry = None
            for dep in updated_deps['fields']:
                if dep['field_id'] == trigger_id:
                    trigger_entry = dep
                    break

            if trigger_entry:
                if 'conditional_fields' not in trigger_entry:
                    trigger_entry['conditional_fields'] = []
                if correction['field_id'] not in trigger_entry['conditional_fields']:
                    trigger_entry['conditional_fields'].append(correction['field_id'])
            else:
                # Create new trigger entry
                updated_deps['fields'].append({
                    'field_id': trigger_id,
                    'conditional_fields': [correction['field_id']],
                    'confidence': correction.get('confidence', 'high')
                })

        # Save
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(updated_deps, f, indent=2, ensure_ascii=False)

        print(f"\n[+] Saved {len(corrections)} corrections to: {output_path}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python review_dependencies.py <schema.json> <dependencies.json> [output.json]")
        print("\nThis tool helps you review and correct Gemini-extracted dependencies.")
        print("\nExample:")
        print("  python review_dependencies.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v7_final.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_dependencies_v2.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_dependencies_corrected.json")
        sys.exit(1)

    schema_path = sys.argv[1]
    deps_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else deps_path.replace('.json', '_corrected.json')

    # Create reviewer
    reviewer = DependencyReviewer(schema_path, deps_path)

    # Show summary
    reviewer.print_summary()

    # Check if interactive mode
    if sys.stdin.isatty():
        print("\nStarting interactive review...")
        corrections = reviewer.review_missing_dependencies(interactive=True)

        if corrections:
            reviewer.save_corrections(corrections, output_path)
            print(f"\nNext steps:")
            print(f"  1. Review: {output_path}")
            print(f"  2. Apply: python apply_dependencies.py {schema_path} {output_path}")
    else:
        print("\nNon-interactive mode - showing analysis only")
        print("\nTo review interactively, run directly from terminal:")
        print(f"  python review_dependencies.py {schema_path} {deps_path} {output_path}")


if __name__ == "__main__":
    main()
