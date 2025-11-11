"""
Schema Merger - Intelligently merge heuristic + Gemini enhancements

Combines the reliable widget extraction from heuristics with the semantic
understanding from Gemini to produce a high-quality final schema.

@version 1.0.0
@date 2025-11-10
"""

from typing import List, Dict, Set, Optional
from collections import Counter

from form_models import (
    FormSchema,
    FormField,
    FieldHelp,
    ValidationRules,
    ConditionalDisplay,
    ConditionalOperator
)
from gemini_models import (
    GeminiEnhancement,
    FieldEnhancement,
    WidgetGroup,
    ConditionalRule
)


class SchemaMerger:
    """
    Merges heuristic schema with Gemini enhancements.

    Strategy:
    - Heuristic schema is the base (guaranteed 100% widget coverage)
    - Gemini enhancements are overlaid where confident
    - Conflicts are logged but Gemini wins if valid
    - Final schema is validated for correctness
    """

    def __init__(self):
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.merge_stats = {
            "fields_enhanced": 0,
            "spoken_names_added": 0,
            "help_text_added": 0,
            "validation_added": 0,
            "groups_applied": 0,
            "conditionals_added": 0,
            "uniqueness_violations": 0,
            "reference_errors": 0
        }

    def merge(
        self,
        heuristic_schema: FormSchema,
        gemini_enhancement: GeminiEnhancement
    ) -> FormSchema:
        """
        Merge heuristic schema with Gemini enhancements.

        Args:
            heuristic_schema: Base schema from heuristic extraction
            gemini_enhancement: Semantic enhancements from Gemini

        Returns:
            Enhanced FormSchema

        Raises:
            ValueError if merge produces invalid schema
        """
        print(f"\n[MERGE] Merging schemas...")
        print(f"   Heuristic fields: {len(heuristic_schema.fields)}")
        print(f"   Gemini enhancements: {len(gemini_enhancement.field_enhancements)}")

        # Start with a copy of heuristic schema
        merged_schema = heuristic_schema.model_copy(deep=True)

        # Build field lookup for fast access
        field_lookup = {field.id: field for field in merged_schema.fields}

        # Apply field enhancements
        self._apply_field_enhancements(
            field_lookup,
            gemini_enhancement.field_enhancements
        )

        # Apply widget groupings
        self._apply_groupings(
            field_lookup,
            gemini_enhancement.widget_groups
        )

        # Apply conditional rules
        self._apply_conditional_rules(
            field_lookup,
            gemini_enhancement.conditional_rules
        )

        # Update fields list
        merged_schema.fields = list(field_lookup.values())

        # Validate final schema
        self._validate_schema(merged_schema)

        # Print summary
        self._print_summary()

        if self.errors:
            raise ValueError(f"Schema merge failed with {len(self.errors)} errors. See logs.")

        return merged_schema

    def _apply_field_enhancements(
        self,
        field_lookup: Dict[str, FormField],
        enhancements: List[FieldEnhancement]
    ) -> None:
        """Apply Gemini's field enhancements to schema."""
        print(f"   Applying field enhancements...")

        for enhancement in enhancements:
            field_id = enhancement.field_id

            if field_id not in field_lookup:
                self.warnings.append(f"Enhancement for unknown field: {field_id}")
                continue

            field = field_lookup[field_id]

            # Apply spoken name
            if enhancement.spoken_name:
                field.spoken_name = enhancement.spoken_name
                self.merge_stats["spoken_names_added"] += 1

            # Apply help text
            if enhancement.help_text or enhancement.format_hint or enhancement.example or enhancement.warning:
                if field.help is None:
                    field.help = FieldHelp()

                if enhancement.help_text:
                    field.help.instructions = enhancement.help_text
                if enhancement.format_hint:
                    field.help.inline = enhancement.format_hint
                if enhancement.example:
                    field.help.example = enhancement.example
                if enhancement.warning:
                    field.help.warning = enhancement.warning

                self.merge_stats["help_text_added"] += 1

            # Apply validation
            if enhancement.format_preset or enhancement.validation_pattern:
                if field.validation is None:
                    field.validation = ValidationRules()

                if enhancement.format_preset:
                    field.validation.format_preset = enhancement.format_preset
                if enhancement.validation_pattern:
                    field.validation.pattern = enhancement.validation_pattern

                self.merge_stats["validation_added"] += 1

            # Apply type correction (if confident)
            if enhancement.suggested_type and enhancement.type_confidence and enhancement.type_confidence > 0.8:
                old_type = field.type
                field.type = enhancement.suggested_type
                self.warnings.append(
                    f"Type changed for {field_id}: {old_type} -> {enhancement.suggested_type} "
                    f"(confidence: {enhancement.type_confidence:.2%})"
                )

            self.merge_stats["fields_enhanced"] += 1

    def _apply_groupings(
        self,
        field_lookup: Dict[str, FormField],
        groups: List[WidgetGroup]
    ) -> None:
        """Apply widget groupings (best effort - may not be accurate)."""
        print(f"   Applying widget groupings (best effort)...")

        for group in groups:
            # Validate all field IDs exist
            valid_fields = [fid for fid in group.field_ids if fid in field_lookup]
            invalid_fields = [fid for fid in group.field_ids if fid not in field_lookup]

            if invalid_fields:
                self.warnings.append(
                    f"Group '{group.purpose}' references unknown fields: {invalid_fields}"
                )

            if not valid_fields:
                continue

            # For radio/checkbox groups, we could update the options
            # But since heuristics already handle this, we just log it
            self.warnings.append(
                f"Group '{group.purpose}' ({group.group_type}): {len(valid_fields)} fields"
            )
            self.merge_stats["groups_applied"] += 1

    def _apply_conditional_rules(
        self,
        field_lookup: Dict[str, FormField],
        rules: List[ConditionalRule]
    ) -> None:
        """Apply conditional logic rules (best effort - may not be accurate)."""
        print(f"   Applying conditional rules (best effort)...")

        for rule in rules:
            # Validate trigger field exists
            if rule.trigger_field_id not in field_lookup:
                self.warnings.append(
                    f"Conditional rule trigger field not found: {rule.trigger_field_id}"
                )
                continue

            # Validate affected fields exist
            valid_affected = [fid for fid in rule.affected_field_ids if fid in field_lookup]
            invalid_affected = [fid for fid in rule.affected_field_ids if fid not in field_lookup]

            if invalid_affected:
                self.warnings.append(
                    f"Conditional rule references unknown fields: {invalid_affected}"
                )

            if not valid_affected:
                continue

            # Apply show_if condition to affected fields (if action is "show")
            if rule.action == "show" and rule.confidence > 0.7:
                for field_id in valid_affected:
                    field = field_lookup[field_id]

                    # Map Gemini operator to our ConditionalOperator
                    try:
                        operator = ConditionalOperator(rule.operator)
                    except ValueError:
                        self.warnings.append(f"Unknown operator: {rule.operator}")
                        continue

                    # Create ConditionalDisplay
                    field.show_if = ConditionalDisplay(
                        field=rule.trigger_field_id,
                        operator=operator,
                        value=rule.value if rule.value is not None else ""
                    )

                self.merge_stats["conditionals_added"] += 1
                self.warnings.append(
                    f"Conditional: {rule.trigger_field_id} {rule.operator} {rule.value} -> "
                    f"show {len(valid_affected)} fields (confidence: {rule.confidence:.2%})"
                )

    def _validate_schema(self, schema: FormSchema) -> None:
        """Validate final schema for correctness."""
        print(f"   Validating merged schema...")

        # Check spoken name uniqueness (CRITICAL)
        spoken_names = [
            field.spoken_name
            for field in schema.fields
            if field.spoken_name
        ]

        duplicates = [
            name for name, count in Counter(spoken_names).items()
            if count > 1
        ]

        if duplicates:
            self.errors.append(
                f"CRITICAL: Duplicate spoken names found: {duplicates}"
            )
            self.merge_stats["uniqueness_violations"] = len(duplicates)

            # Log which fields have duplicate names
            for dup_name in duplicates:
                dup_fields = [
                    field.id for field in schema.fields
                    if field.spoken_name == dup_name
                ]
                self.errors.append(f"  '{dup_name}' used by: {dup_fields}")

        # Check field ID uniqueness
        field_ids = [field.id for field in schema.fields]
        id_duplicates = [
            fid for fid, count in Counter(field_ids).items()
            if count > 1
        ]

        if id_duplicates:
            self.errors.append(f"Duplicate field IDs: {id_duplicates}")

        # Check conditional references are valid
        all_field_ids = set(field_ids)
        for field in schema.fields:
            if field.show_if:
                if field.show_if.field not in all_field_ids:
                    self.errors.append(
                        f"Field {field.id} has show_if referencing unknown field: {field.show_if.field}"
                    )
                    self.merge_stats["reference_errors"] += 1

    def _print_summary(self) -> None:
        """Print merge summary."""
        print(f"\n[SUMMARY] Merge Summary:")
        print(f"   Fields enhanced: {self.merge_stats['fields_enhanced']}")
        print(f"   Spoken names added: {self.merge_stats['spoken_names_added']}")
        print(f"   Help text added: {self.merge_stats['help_text_added']}")
        print(f"   Validation rules added: {self.merge_stats['validation_added']}")
        print(f"   Widget groups applied: {self.merge_stats['groups_applied']}")
        print(f"   Conditional rules added: {self.merge_stats['conditionals_added']}")

        if self.warnings:
            print(f"\n[WARN] Warnings ({len(self.warnings)}):")
            for warning in self.warnings[:10]:  # Show first 10
                print(f"   - {warning}")
            if len(self.warnings) > 10:
                print(f"   ... and {len(self.warnings) - 10} more")

        if self.errors:
            print(f"\n[ERROR] Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"   - {error}")

        if self.merge_stats["uniqueness_violations"] > 0:
            print(f"\n[CRITICAL] {self.merge_stats['uniqueness_violations']} spoken name uniqueness violations!")
            print(f"   This will break JIT field loading for token reduction.")


def merge_schemas(
    heuristic_schema: FormSchema,
    gemini_enhancement: GeminiEnhancement
) -> FormSchema:
    """
    Convenience function for one-shot schema merging.

    Args:
        heuristic_schema: Base schema from heuristic extraction
        gemini_enhancement: Semantic enhancements from Gemini

    Returns:
        Enhanced FormSchema

    Raises:
        ValueError if merge produces invalid schema
    """
    merger = SchemaMerger()
    return merger.merge(heuristic_schema, gemini_enhancement)
