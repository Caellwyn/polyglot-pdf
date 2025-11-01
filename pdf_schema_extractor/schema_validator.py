#!/usr/bin/env python3
"""
Comprehensive Schema Validator

Validates schema for voice AI and PDF viewer readiness:
1. Conditional logic completeness
2. Trigger field references
3. JavaScript unlock instructions
4. Validation rules
5. Field relationships
"""

import json
import sys
from typing import Dict, List, Set, Tuple
from collections import defaultdict


class SchemaValidator:
    def __init__(self, schema: Dict):
        self.schema = schema
        self.fields_by_id = {f['id']: f for f in schema.get('fields', [])}
        self.errors = []
        self.warnings = []
        self.info = []

    def validate_all(self) -> Dict:
        """Run all validation checks."""
        print("Running comprehensive schema validation...\n")

        self.check_conditional_trigger_references()
        self.check_javascript_unlock_instructions()
        self.check_conditional_completeness()
        self.check_required_field_logic()
        self.check_validation_rules()
        self.check_voice_ai_readiness()
        self.check_pdf_field_name_coverage()

        return {
            'errors': self.errors,
            'warnings': self.warnings,
            'info': self.info,
            'total_issues': len(self.errors) + len(self.warnings)
        }

    def check_conditional_trigger_references(self):
        """Check that all trigger_field references point to existing fields."""
        print("[1/7] Checking conditional trigger references...")

        missing_triggers = []
        for field in self.schema['fields']:
            cond = field.get('conditional_logic') or field.get('help', {}).get('conditional_logic')

            if cond and isinstance(cond, dict):
                trigger_field = cond.get('trigger_field')

                if trigger_field and trigger_field not in self.fields_by_id:
                    missing_triggers.append({
                        'field_id': field['id'],
                        'trigger_field': trigger_field,
                        'issue': 'Trigger field does not exist in schema'
                    })

        if missing_triggers:
            self.errors.append({
                'category': 'missing_trigger_fields',
                'count': len(missing_triggers),
                'details': missing_triggers
            })
            print(f"  ERROR: {len(missing_triggers)} fields reference non-existent triggers")
        else:
            print(f"  PASS: All trigger field references are valid")

    def check_javascript_unlock_instructions(self):
        """Check that fields with flip_readonly_bit have JavaScript instructions."""
        print("\n[2/7] Checking JavaScript unlock instructions...")

        missing_js_instructions = []
        for field in self.schema['fields']:
            cond = field.get('conditional_logic') or field.get('help', {}).get('conditional_logic')

            if cond and isinstance(cond, dict):
                unlock_method = cond.get('unlock_method')

                if unlock_method == 'flip_readonly_bit':
                    unlock_instructions = cond.get('unlock_instructions', {})

                    if 'javascript' not in unlock_instructions:
                        missing_js_instructions.append({
                            'field_id': field['id'],
                            'has_python': 'python' in unlock_instructions or 'pdf_field_flag_change' in cond,
                            'issue': 'Missing JavaScript unlock instructions for client-side unlocking'
                        })

        if missing_js_instructions:
            self.warnings.append({
                'category': 'missing_js_unlock_instructions',
                'count': len(missing_js_instructions),
                'details': missing_js_instructions
            })
            print(f"  WARNING: {len(missing_js_instructions)} fields need JavaScript unlock instructions")
        else:
            print(f"  PASS: All unlock fields have JavaScript instructions")

    def check_conditional_completeness(self):
        """Check that conditionals have all required fields."""
        print("\n[3/7] Checking conditional completeness...")

        incomplete_conditionals = []
        for field in self.schema['fields']:
            cond = field.get('conditional_logic') or field.get('help', {}).get('conditional_logic')

            if cond and isinstance(cond, dict):
                missing_fields = []

                # Check required fields based on type
                cond_type = cond.get('type')

                if cond_type in ['conditional_visibility', 'needs_manual_parsing']:
                    if not cond.get('trigger_field'):
                        missing_fields.append('trigger_field')

                if cond_type == 'conditional_visibility':
                    if not cond.get('unlock_method'):
                        missing_fields.append('unlock_method')

                # Check for manual review flags
                needs_review = 'note' in cond and 'manual' in cond.get('note', '').lower()

                if missing_fields or needs_review:
                    incomplete_conditionals.append({
                        'field_id': field['id'],
                        'type': cond_type,
                        'missing_fields': missing_fields,
                        'needs_manual_review': needs_review,
                        'note': cond.get('note')
                    })

        if incomplete_conditionals:
            manual_count = sum(1 for c in incomplete_conditionals if c['needs_manual_review'])
            self.warnings.append({
                'category': 'incomplete_conditionals',
                'count': len(incomplete_conditionals),
                'manual_review_needed': manual_count,
                'details': incomplete_conditionals
            })
            print(f"  WARNING: {len(incomplete_conditionals)} conditionals incomplete ({manual_count} need manual review)")
        else:
            print(f"  PASS: All conditionals are complete")

    def check_required_field_logic(self):
        """Check for fields that should be conditionally required."""
        print("\n[4/7] Checking required field logic...")

        conditional_required_missing = []
        for field in self.schema['fields']:
            cond = field.get('conditional_logic') or field.get('help', {}).get('conditional_logic')

            if cond and isinstance(cond, dict):
                # If field has conditional logic and is required, should have required_if
                if field.get('required') and not field.get('required_if'):
                    conditional_required_missing.append({
                        'field_id': field['id'],
                        'issue': 'Field is required but lacks required_if metadata',
                        'suggestion': f'Add required_if based on trigger: {cond.get("trigger_field")}'
                    })

        if conditional_required_missing:
            self.info.append({
                'category': 'conditional_required_missing',
                'count': len(conditional_required_missing),
                'details': conditional_required_missing
            })
            print(f"  INFO: {len(conditional_required_missing)} fields could use required_if metadata")
        else:
            print(f"  PASS: Required field logic is appropriate")

    def check_validation_rules(self):
        """Check validation rules for completeness."""
        print("\n[5/7] Checking validation rules...")

        fields_with_validation = 0
        validation_issues = []

        for field in self.schema['fields']:
            validation = field.get('validation')

            if validation:
                fields_with_validation += 1

                # Check for exact_length without max_length
                if validation.get('exact_length') and not field.get('max_length'):
                    validation_issues.append({
                        'field_id': field['id'],
                        'issue': 'Has exact_length validation but no max_length field property',
                        'exact_length': validation.get('exact_length')
                    })

        print(f"  INFO: {fields_with_validation} fields have validation rules")

        if validation_issues:
            self.warnings.append({
                'category': 'validation_rule_issues',
                'count': len(validation_issues),
                'details': validation_issues
            })
            print(f"  WARNING: {len(validation_issues)} validation rule issues found")

    def check_voice_ai_readiness(self):
        """Check schema readiness for voice AI."""
        print("\n[6/7] Checking voice AI readiness...")

        # Check conditional index exists
        if 'conditional_index' not in self.schema:
            self.errors.append({
                'category': 'missing_conditional_index',
                'issue': 'Schema lacks conditional_index for efficient conditional lookups',
                'fix': 'Run build_conditional_index.py'
            })
            print(f"  ERROR: Missing conditional_index")
        else:
            index_stats = self.schema['conditional_index'].get('stats', {})
            print(f"  PASS: Conditional index present")
            print(f"    Triggers: {index_stats.get('total_trigger_fields', 0)}")
            print(f"    Dependents: {index_stats.get('total_dependent_fields', 0)}")
            print(f"    Relationships: {index_stats.get('total_conditional_relationships', 0)}")

        # Check for fields with controls_fields
        trigger_fields = 0
        for field in self.schema['fields']:
            if 'controls_fields' in field:
                trigger_fields += 1

        print(f"    Trigger fields with controls_fields: {trigger_fields}")

    def check_pdf_field_name_coverage(self):
        """Check that all fields have pdf_field_name or consolidated_widgets."""
        print("\n[7/7] Checking PDF field name coverage...")

        missing_pdf_mapping = []
        for field in self.schema['fields']:
            has_pdf_name = field.get('pdf_field_name')
            has_consolidated = field.get('consolidated_widgets')

            if not has_pdf_name and not has_consolidated:
                missing_pdf_mapping.append({
                    'field_id': field['id'],
                    'type': field.get('type'),
                    'issue': 'No PDF field mapping (neither pdf_field_name nor consolidated_widgets)'
                })

        if missing_pdf_mapping:
            self.warnings.append({
                'category': 'missing_pdf_field_mapping',
                'count': len(missing_pdf_mapping),
                'details': missing_pdf_mapping
            })
            print(f"  WARNING: {len(missing_pdf_mapping)} fields lack PDF field mapping")
        else:
            print(f"  PASS: All fields have PDF field mappings")

    def print_summary(self, results: Dict):
        """Print validation summary."""
        print(f"\n{'='*70}")
        print("VALIDATION SUMMARY")
        print(f"{'='*70}")

        print(f"\nErrors: {len(results['errors'])}")
        for error in results['errors']:
            print(f"  - {error['category']}: ", end='')
            if 'count' in error:
                print(f"{error['count']} issues")
            else:
                print(error.get('issue', ''))

        print(f"\nWarnings: {len(results['warnings'])}")
        for warning in results['warnings']:
            print(f"  - {warning['category']}: {warning['count']} issues")

        print(f"\nInfo: {len(results['info'])}")
        for info_item in results['info']:
            print(f"  - {info_item['category']}: {info_item['count']} items")

        print(f"\nTotal Issues: {results['total_issues']}")

        if results['total_issues'] == 0:
            print(f"\n[SUCCESS] Schema is fully validated and ready for voice AI!")
        elif len(results['errors']) == 0:
            print(f"\n[WARNINGS ONLY] Schema is functional but has {len(results['warnings'])} warnings to address")
        else:
            print(f"\n[NEEDS FIXES] Schema has {len(results['errors'])} errors that must be fixed")


def main():
    if len(sys.argv) < 2:
        print("Usage: python schema_validator.py <schema.json> [--save-report]")
        sys.exit(1)

    schema_path = sys.argv[1]
    save_report = '--save-report' in sys.argv

    # Load schema
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Run validation
    validator = SchemaValidator(schema)
    results = validator.validate_all()

    # Print summary
    validator.print_summary(results)

    # Save report if requested
    if save_report:
        report_path = schema_path.replace('.json', '_validation_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nValidation report saved to: {report_path}")

    # Exit with error code if there are errors
    sys.exit(1 if len(results['errors']) > 0 else 0)


if __name__ == "__main__":
    main()
