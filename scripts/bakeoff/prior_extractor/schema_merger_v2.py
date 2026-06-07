"""
Schema merger for V2 - handles batched responses and multiple enhancement types.

Combines:
- Heuristic extraction (baseline)
- Gemini spoken names + help text (batched)
- Gemini groupings (radio/checkbox only)
- Gemini conditionals (batched, optional)
"""

from typing import List, Dict, Any, Optional
from form_models import FormSchema, FormField
from gemini_models_v2 import (
    SpokenNamesResponse,
    GroupingsResponse,
    ConditionalsResponse
)


class SchemaMergerV2:
    """Merges heuristic schema with Gemini V2 enhancements."""

    def __init__(self, heuristic_schema: FormSchema):
        """Initialize with baseline heuristic schema."""
        self.schema = heuristic_schema

    def apply_spoken_names(
        self,
        responses: List[SpokenNamesResponse],
        min_confidence: float = 0.7
    ) -> int:
        """
        Apply spoken names and help text from batched responses.

        Returns:
            Number of fields enhanced
        """
        # Concatenate all field enhancements from all batches
        all_enhancements = []
        for response in responses:
            all_enhancements.extend(response.field_enhancements)

        # Build lookup map
        enhancement_map = {
            enh.field_id: enh
            for enh in all_enhancements
            if enh.confidence >= min_confidence
        }

        # Validate spoken name uniqueness (CRITICAL)
        spoken_names = [enh.spoken_name for enh in enhancement_map.values()]
        if len(spoken_names) != len(set(spoken_names)):
            duplicates = [name for name in spoken_names if spoken_names.count(name) > 1]
            raise ValueError(
                f"CRITICAL: Non-unique spoken names detected: {set(duplicates)}\n"
                "Spoken names must be unique for token reduction in voice app."
            )

        # Apply enhancements
        enhanced_count = 0
        for field in self.schema.fields:
            if field.id in enhancement_map:
                enh = enhancement_map[field.id]
                field.spoken_name = enh.spoken_name
                if enh.help_text:
                    # Store in field.help if it exists
                    if not field.help:
                        from form_models import FieldHelp
                        field.help = FieldHelp()
                    field.help.inline = enh.help_text
                enhanced_count += 1

        return enhanced_count

    def apply_groupings(
        self,
        response: GroupingsResponse,
        min_confidence: float = 0.7
    ) -> int:
        """
        Apply widget groupings from Gemini response.

        Returns:
            Number of groups applied
        """
        applied_count = 0

        for group in response.widget_groups:
            if group.confidence < min_confidence:
                continue

            # Verify all field IDs exist
            valid_field_ids = {field.id for field in self.schema.fields}
            group_field_ids = [
                fid for fid in group.field_ids
                if fid in valid_field_ids
            ]

            if len(group_field_ids) != len(group.field_ids):
                missing = set(group.field_ids) - valid_field_ids
                print(f"[WARN] Group '{group.group_name}' references missing fields: {missing}")

            if len(group_field_ids) < 2:
                continue  # Need at least 2 fields for a group

            # Apply grouping to fields
            for field in self.schema.fields:
                if field.id in group_field_ids:
                    # Set group_id and group_label
                    field.group_id = group.group_name
                    field.group_label = group.group_label
                    # Note: is_exclusive is handled by field type (radio vs checkbox)

            applied_count += 1

        return applied_count

    def apply_conditionals(
        self,
        responses: List[ConditionalsResponse],
        min_confidence: float = 0.7
    ) -> int:
        """
        Apply conditional rules from batched responses.

        Returns:
            Number of rules applied
        """
        # Concatenate all rules from all batches
        all_rules = []
        for response in responses:
            all_rules.extend(response.conditional_rules)

        # Filter by confidence
        valid_rules = [
            rule for rule in all_rules
            if rule.confidence >= min_confidence
        ]

        # Build field ID lookup
        valid_field_ids = {field.id for field in self.schema.fields}

        applied_count = 0
        for rule in valid_rules:
            # Verify field IDs exist
            if rule.field_id not in valid_field_ids:
                print(f"[WARN] Conditional references missing field: {rule.field_id}")
                continue
            if rule.trigger_field_id not in valid_field_ids:
                print(f"[WARN] Conditional references missing trigger: {rule.trigger_field_id}")
                continue

            # Find target field and apply rule
            for field in self.schema.fields:
                if field.id == rule.field_id:
                    # Store conditional in show_if or controls_fields
                    # For now, just track in conditional_fields
                    if not field.conditional_fields:
                        field.conditional_fields = []

                    field.conditional_fields.append(rule.trigger_field_id)
                    applied_count += 1
                    break

        return applied_count

    def get_enhanced_schema(self) -> FormSchema:
        """Return the enhanced schema."""
        return self.schema

    def get_enhancement_stats(self) -> Dict[str, Any]:
        """Get statistics about applied enhancements."""
        stats = {
            "total_fields": len(self.schema.fields),
            "fields_with_spoken_names": 0,
            "fields_with_help_text": 0,
            "fields_with_groups": 0,
            "fields_with_conditionals": 0,
            "unique_spoken_names": set()
        }

        for field in self.schema.fields:
            if field.spoken_name:
                stats["fields_with_spoken_names"] += 1
                stats["unique_spoken_names"].add(field.spoken_name)

            if field.help and field.help.inline:
                stats["fields_with_help_text"] += 1

            if field.group_id:
                stats["fields_with_groups"] += 1

            if field.conditional_fields:
                stats["fields_with_conditionals"] += 1

        stats["unique_spoken_names"] = len(stats["unique_spoken_names"])

        return stats
