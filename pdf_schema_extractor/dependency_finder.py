#!/usr/bin/env python3
"""
Dependency Finder - Automatically identify trigger fields for conditional logic.

Uses heuristics and pattern matching to find the most likely trigger field
for each conditional dependency.
"""

import json
import re
import sys
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher


class DependencyFinder:
    """Find trigger fields for conditional dependencies."""

    def __init__(self, schema: Dict):
        self.schema = schema
        self.fields_by_id = {f['id']: f for f in schema.get('fields', [])}
        self.fields_by_section = {}

        # Group fields by section for proximity matching
        for field in schema['fields']:
            section = field.get('section', 'Unknown')
            if section not in self.fields_by_section:
                self.fields_by_section[section] = []
            self.fields_by_section[section].append(field)

    def find_trigger_for_pre_populated(self, conditional: Dict, field: Dict) -> Optional[Dict]:
        """
        Find trigger for pre-populated fields.

        Pattern: "Pre-populated from <field_id>"
        """
        conditional_text = conditional.get('original_text', '') or conditional.get('description', '')

        # Extract source field ID
        match = re.search(r'pre-populated from ([a-z0-9_\[\]]+)', conditional_text.lower())
        if match:
            source_field = match.group(1)

            # Verify source field exists
            if source_field in self.fields_by_id:
                return {
                    'trigger_field': source_field,
                    'trigger_value': None,  # Copy value directly
                    'confidence': 1.0,
                    'method': 'pre_populated_parse',
                    'reason': f'Direct reference in conditional text'
                }

        return None

    def find_trigger_for_apt_suite_floor(self, conditional: Dict, field: Dict) -> Optional[Dict]:
        """
        Find trigger for apartment/suite/floor fields.

        Pattern: Field like "p6_line3b_aptsteflrnumber" triggered by checkbox
        """
        field_id = field['id']

        # Check if this is an apt/ste/flr number field
        if 'aptsteflrnumber' not in field_id and 'aptsteflt' not in field_id:
            return None

        # Find the base field name (remove _aptsteflrnumber)
        base_id = field_id.replace('_aptsteflrnumber', '').replace('_aptsteflt', '')

        # Look for checkbox field with similar base
        # Pattern: p6_line3b_aptsteflrnumber -> p6_line3a_aptsteflt (checkbox)
        # Try variations
        candidates = []

        # Strategy 1: Same base, different suffix
        for suffix in ['_aptsteflt', '_apt', '_ste', '_checkbox']:
            candidate_id = base_id + suffix
            if candidate_id in self.fields_by_id:
                candidates.append({
                    'trigger_field': candidate_id,
                    'confidence': 0.9,
                    'reason': 'Same base field name with checkbox suffix'
                })

        # Strategy 2: Previous line in same part
        # p6_line3b -> p6_line3a
        match = re.match(r'(p\d+_line\d+)([a-z])', base_id)
        if match:
            base_part = match.group(1)
            current_suffix = match.group(2)

            # Try previous letter
            prev_suffix = chr(ord(current_suffix) - 1)
            for suffix in ['_aptsteflt', '_checkbox']:
                candidate_id = f"{base_part}{prev_suffix}{suffix}"
                if candidate_id in self.fields_by_id:
                    candidates.append({
                        'trigger_field': candidate_id,
                        'confidence': 0.85,
                        'reason': 'Previous line in sequence with checkbox suffix'
                    })

        # Return highest confidence match
        if candidates:
            candidates.sort(key=lambda x: x['confidence'], reverse=True)
            result = candidates[0]
            result['trigger_value'] = True
            result['method'] = 'apt_suite_floor_pattern'
            return result

        return None

    def find_trigger_for_accommodation(self, conditional: Dict, field: Dict) -> Optional[Dict]:
        """
        Find trigger for accommodation fields.

        Pattern: "Show only if 'Yes' is selected for requesting accommodations"

        Look for a parent checkbox like "Do you need accommodations?" or "Are you requesting accommodation?"
        """
        section = field.get('section', '')

        # Search for accommodation yes/no question in same section
        section_fields = self.fields_by_section.get(section, [])

        candidates = []
        field_idx = self.schema['fields'].index(field)

        for candidate in section_fields:
            candidate_id = candidate['id']
            candidate_idx = self.schema['fields'].index(candidate)

            candidate_name = (candidate.get('name', '') + ' ' + candidate.get('label', '')).lower()

            # Look for parent "are you requesting" question (not individual disability checkboxes)
            is_parent_question = (
                'are you requesting' in candidate_name or
                'do you need' in candidate_name or
                'request an accommodation' in candidate_name
            )

            # Check if it's a yes/no radio button specifically
            if is_parent_question and candidate.get('type') == 'radio':
                # Check if it has yes/no options
                options = candidate.get('options', [])
                has_yes = any('yes' in str(opt).lower() for opt in options)
                has_no = any('no' in str(opt).lower() for opt in options)

                if has_yes and has_no:
                    # This is likely the parent yes/no question
                    # Calculate proximity score (closer = better, either direction)
                    proximity = abs(field_idx - candidate_idx)
                    proximity_score = 1.0 if proximity <= 10 else 0.9

                    # Slight preference for candidate coming before (more typical)
                    direction_score = 1.0 if candidate_idx < field_idx else 0.95

                    candidates.append({
                        'trigger_field': candidate_id,
                        'trigger_value': True,  # Yes selected
                        'confidence': 0.95 * proximity_score * direction_score,
                        'reason': f'Parent accommodation yes/no question (proximity={proximity})',
                        'candidate_name': candidate.get('name', candidate_id)
                    })

        # Return highest confidence match
        if candidates:
            candidates.sort(key=lambda x: x['confidence'], reverse=True)
            result = candidates[0]
            result['method'] = 'accommodation_pattern'
            return result

        return None

    def find_trigger_for_conditional_pr(self, conditional: Dict, field: Dict) -> Optional[Dict]:
        """
        Find trigger for "conditional permanent resident" fields.

        Pattern: "Show only if you are a conditional permanent resident"

        Look for Part 2 radio button with "Conditional Permanent Resident" option.
        """
        # These fields are in Part 2, so look for status selection field
        section = field.get('section', '')
        field_idx = self.schema['fields'].index(field)

        candidates = []
        for candidate in self.schema['fields']:
            candidate_id = candidate['id']
            candidate_idx = self.schema['fields'].index(candidate)

            # Must come BEFORE this field
            if candidate_idx >= field_idx:
                continue

            # Look for radio buttons (status selection is usually radio)
            if candidate.get('type') != 'radio':
                continue

            # Check if it has "Conditional Permanent Resident" as an option
            options = candidate.get('options', [])
            conditional_pr_option = None

            for opt in options:
                opt_label = opt.get('label', '') if isinstance(opt, dict) else str(opt)
                opt_value = opt.get('value', '') if isinstance(opt, dict) else str(opt)

                if 'conditional permanent resident' in opt_label.lower():
                    conditional_pr_option = opt_value
                    break

            if conditional_pr_option:
                # Calculate proximity score
                proximity = field_idx - candidate_idx
                proximity_score = 1.0 if proximity <= 10 else 0.9

                candidates.append({
                    'trigger_field': candidate_id,
                    'trigger_value': conditional_pr_option,
                    'confidence': 0.95 * proximity_score,
                    'reason': f'Radio button with "Conditional Permanent Resident" option (proximity={proximity})',
                    'candidate_name': candidate.get('name', candidate_id)
                })

        # Return highest confidence match
        if candidates:
            candidates.sort(key=lambda x: x['confidence'], reverse=True)
            result = candidates[0]
            result['method'] = 'conditional_pr_pattern'
            return result

        return None

    def find_trigger_for_field(self, field: Dict) -> Optional[Dict]:
        """
        Main finder - tries all strategies to find trigger field.

        Returns best match with confidence score.
        """
        # Get conditional logic
        cond = field.get('conditional_logic') or field.get('help', {}).get('conditional_logic')

        if not cond or not isinstance(cond, dict):
            return None

        # Skip if already has trigger field
        if cond.get('trigger_field') and cond['trigger_field'] in self.fields_by_id:
            return None

        # Skip signatures
        if 'signature' in field.get('type', '') or 'signature' in field.get('name', '').lower():
            return None

        conditional_text = (cond.get('original_text', '') or cond.get('description', '')).lower()

        # Try different strategies based on conditional type/text
        strategies = []

        if 'pre-populated' in conditional_text:
            strategies.append(self.find_trigger_for_pre_populated)

        if 'apartment' in conditional_text or 'aptsteflrnumber' in field['id']:
            strategies.append(self.find_trigger_for_apt_suite_floor)

        if 'accommodation' in conditional_text or 'disability' in conditional_text:
            strategies.append(self.find_trigger_for_accommodation)

        if 'conditional permanent resident' in conditional_text:
            strategies.append(self.find_trigger_for_conditional_pr)

        # Try each strategy
        best_match = None
        for strategy in strategies:
            match = strategy(cond, field)
            if match:
                if not best_match or match['confidence'] > best_match['confidence']:
                    best_match = match

        return best_match

    def find_all_dependencies(self, min_confidence: float = 0.7) -> List[Dict]:
        """
        Find trigger fields for all fields with incomplete conditionals.

        Returns list of matches with confidence scores.
        """
        matches = []

        for field in self.schema['fields']:
            match = self.find_trigger_for_field(field)

            if match and match['confidence'] >= min_confidence:
                matches.append({
                    'field_id': field['id'],
                    'field_name': field.get('name', ''),
                    'section': field.get('section', ''),
                    'trigger_field': match['trigger_field'],
                    'trigger_value': match['trigger_value'],
                    'confidence': match['confidence'],
                    'method': match['method'],
                    'reason': match['reason']
                })

        return matches

    def apply_dependencies(self, dependencies: List[Dict], min_confidence: float = 0.8) -> int:
        """
        Apply found dependencies to schema.

        Only applies high-confidence matches (>= min_confidence).
        """
        applied_count = 0

        for dep in dependencies:
            if dep['confidence'] < min_confidence:
                continue

            field = self.fields_by_id.get(dep['field_id'])
            if not field:
                continue

            # Get conditional logic
            cond = field.get('conditional_logic')
            if not cond:
                cond = field.get('help', {}).get('conditional_logic')

            if cond and isinstance(cond, dict):
                # Update trigger field
                cond['trigger_field'] = dep['trigger_field']
                cond['trigger_value'] = dep['trigger_value']

                # Add note about auto-discovery
                if 'note' in cond:
                    cond['note'] = f"Auto-discovered trigger (confidence={dep['confidence']:.2f})"

                applied_count += 1

        return applied_count


def main():
    if len(sys.argv) < 2:
        print("Usage: python dependency_finder.py <schema.json> [--apply] [--min-confidence=0.8]")
        print("\nOptions:")
        print("  --apply            Apply high-confidence matches to schema")
        print("  --min-confidence   Minimum confidence for applying (default: 0.8)")
        sys.exit(1)

    schema_path = sys.argv[1]
    apply_changes = '--apply' in sys.argv

    # Parse min-confidence
    min_confidence = 0.8
    for arg in sys.argv:
        if arg.startswith('--min-confidence='):
            min_confidence = float(arg.split('=')[1])

    # Load schema
    print("Loading schema...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Find dependencies
    print("\nSearching for trigger field dependencies...\n")
    finder = DependencyFinder(schema)
    dependencies = finder.find_all_dependencies(min_confidence=0.7)

    # Print results
    print(f"{'='*70}")
    print("DEPENDENCY FINDER RESULTS")
    print(f"{'='*70}")
    print(f"Found {len(dependencies)} potential dependencies\n")

    # Group by confidence
    high_confidence = [d for d in dependencies if d['confidence'] >= 0.9]
    medium_confidence = [d for d in dependencies if 0.8 <= d['confidence'] < 0.9]
    low_confidence = [d for d in dependencies if 0.7 <= d['confidence'] < 0.8]

    print(f"High confidence (>= 0.9): {len(high_confidence)}")
    print(f"Medium confidence (0.8-0.9): {len(medium_confidence)}")
    print(f"Low confidence (0.7-0.8): {len(low_confidence)}")

    # Show all matches
    print(f"\n{'='*70}")
    print("ALL MATCHES")
    print(f"{'='*70}\n")

    for dep in sorted(dependencies, key=lambda x: x['confidence'], reverse=True):
        print(f"Field: {dep['field_id']}")
        print(f"  Name: {dep['field_name']}")
        print(f"  Trigger: {dep['trigger_field']} (value={dep['trigger_value']})")
        print(f"  Confidence: {dep['confidence']:.2f}")
        print(f"  Method: {dep['method']}")
        print(f"  Reason: {dep['reason']}")
        print()

    # Apply if requested
    if apply_changes:
        print(f"{'='*70}")
        print(f"APPLYING HIGH-CONFIDENCE MATCHES (>= {min_confidence})")
        print(f"{'='*70}\n")

        applied = finder.apply_dependencies(dependencies, min_confidence=min_confidence)

        # Save updated schema
        output_path = schema_path.replace('.json', '_with_dependencies.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)

        print(f"Applied {applied} dependencies to schema")
        print(f"Saved to: {output_path}")
        print(f"\nNext steps:")
        print(f"  1. Review applied dependencies")
        print(f"  2. Run build_conditional_index.py to rebuild index")
        print(f"  3. Run schema_validator.py to verify")
    else:
        print(f"{'='*70}")
        print("DRY RUN - No changes applied")
        print(f"{'='*70}")
        print(f"\nTo apply high-confidence matches, run:")
        print(f"  python dependency_finder.py {schema_path} --apply --min-confidence={min_confidence}")


if __name__ == "__main__":
    main()
