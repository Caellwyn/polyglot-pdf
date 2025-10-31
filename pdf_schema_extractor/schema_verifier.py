#!/usr/bin/env python3
"""
Multi-layer schema verification system.
Validates PDF schemas WITHOUT requiring ground truth.

Verification Layers:
1. Widget Coverage - Every PDF widget must be in schema (checks consolidated_widgets)
2. Type Compatibility - Schema types must match widget types
3. Structural Consistency - Internal logic checks
"""

import json
import fitz
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from widget_inventory import extract_widget_inventory

@dataclass
class VerificationResult:
    """Result of verification."""
    layer: str
    passed: bool
    score: float  # 0.0 - 1.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class VerificationReport:
    """Complete verification report."""
    overall_passed: bool
    confidence_score: float
    layers: List[VerificationResult]
    summary: Dict[str, Any]

class SchemaVerifier:
    """Multi-layer schema verifier."""

    # Type compatibility matrix
    TYPE_COMPATIBILITY = {
        # PDF widget type → allowed schema types
        "text": ["text", "textarea", "date", "email", "tel", "number"],
        "checkbox": ["checkbox", "radio"],
        "radio": ["radio"],
        "select": ["select"],
        # Signature widgets in government PDFs are often used as secure text inputs
        "signature": ["signature", "text", "textarea", "date", "email", "tel", "number"],
    }

    def verify(self, pdf_path: str, schema: Dict[str, Any]) -> VerificationReport:
        """
        Run all verification layers.

        Args:
            pdf_path: Path to PDF file
            schema: Candidate schema to verify

        Returns:
            Complete verification report
        """
        print(f"\n{'='*60}")
        print(f"SCHEMA VERIFICATION")
        print(f"{'='*60}")
        print(f"PDF: {pdf_path}")
        print(f"Schema fields: {len(schema.get('fields', []))}")

        layers = []

        # Layer 1: Widget Coverage (CRITICAL)
        print(f"\n[Layer 1/3] Widget Coverage...")
        coverage_result = self.verify_widget_coverage(pdf_path, schema)
        layers.append(coverage_result)
        print(f"  Score: {coverage_result.score*100:.1f}% - {'PASS' if coverage_result.passed else 'FAIL'}")

        # Layer 2: Type Compatibility (CRITICAL)
        print(f"\n[Layer 2/3] Type Compatibility...")
        type_result = self.verify_type_compatibility(pdf_path, schema)
        layers.append(type_result)
        print(f"  Score: {type_result.score*100:.1f}% - {'PASS' if type_result.passed else 'FAIL'}")

        # Layer 3: Structural Consistency (HIGH)
        print(f"\n[Layer 3/3] Structural Consistency...")
        structure_result = self.verify_structural_consistency(schema)
        layers.append(structure_result)
        print(f"  Score: {structure_result.score*100:.1f}% - {'PASS' if structure_result.passed else 'FAIL'}")

        # Calculate overall result
        critical_passed = all(l.passed for l in layers[:2])  # Layers 1-2 are critical
        confidence_score = sum(l.score for l in layers) / len(layers)

        # Summary
        summary = {
            "total_layers": len(layers),
            "layers_passed": sum(1 for l in layers if l.passed),
            "critical_passed": critical_passed,
            "confidence_score": confidence_score,
            "field_count": len(schema.get('fields', [])),
            "total_errors": sum(len(l.errors) for l in layers),
            "total_warnings": sum(len(l.warnings) for l in layers)
        }

        report = VerificationReport(
            overall_passed=critical_passed,
            confidence_score=confidence_score,
            layers=layers,
            summary=summary
        )

        print(f"\n{'='*60}")
        print(f"OVERALL: {'PASS' if report.overall_passed else 'FAIL'} (confidence: {confidence_score*100:.1f}%)")
        print(f"{'='*60}\n")

        return report

    def verify_widget_coverage(self, pdf_path: str, schema: Dict[str, Any]) -> VerificationResult:
        """
        Verify that all PDF widgets are accounted for in schema.
        Uses FILTERED widget inventory (excludes hidden/readonly/signature fields).
        CRITICAL: Must have 95%+ coverage to pass.
        """
        # Use filtered widget inventory (same as extractors use)
        # This automatically excludes hidden, readonly, signature, barcode fields
        filtered_widgets = extract_widget_inventory(pdf_path)
        pdf_field_names = {w['field_name'] for w in filtered_widgets}

        # Get all PDF field names from schema
        schema_pdf_names = set()
        for field in schema.get("fields", []):
            self._collect_pdf_field_names(field, schema_pdf_names)

        # Calculate coverage
        if not pdf_field_names:
            return VerificationResult(
                layer="widget_coverage",
                passed=False,
                score=0.0,
                errors=["No PDF widgets found"]
            )

        covered = schema_pdf_names & pdf_field_names
        missing = pdf_field_names - schema_pdf_names
        hallucinated = schema_pdf_names - pdf_field_names

        coverage = len(covered) / len(pdf_field_names)
        passed = coverage >= 0.95

        errors = []
        warnings = []

        if coverage < 0.95:
            errors.append(f"Coverage is only {coverage*100:.1f}% (need 95%+)")

        if missing:
            if len(missing) <= 10:
                warnings.append(f"Missing {len(missing)} widgets: {list(missing)}")
            else:
                warnings.append(f"Missing {len(missing)} widgets (first 10): {list(missing)[:10]}")

        if hallucinated:
            if len(hallucinated) <= 10:
                warnings.append(f"Hallucinated {len(hallucinated)} names: {list(hallucinated)}")
            else:
                warnings.append(f"Hallucinated {len(hallucinated)} names (first 10): {list(hallucinated)[:10]}")

        return VerificationResult(
            layer="widget_coverage",
            passed=passed,
            score=coverage,
            errors=errors,
            warnings=warnings,
            details={
                "total_widgets": len(pdf_field_names),
                "covered_widgets": len(covered),
                "missing_widgets": len(missing),
                "hallucinated_names": len(hallucinated),
                "coverage_percent": coverage * 100
            }
        )

    def verify_type_compatibility(self, pdf_path: str, schema: Dict[str, Any]) -> VerificationResult:
        """
        Verify that schema field types are compatible with PDF widget types.
        Uses FILTERED widget inventory (excludes hidden/readonly/signature fields).
        CRITICAL: Must have 100% compatibility to pass.
        """
        # Use filtered widget inventory (same as extractors use)
        filtered_widgets = extract_widget_inventory(pdf_path)

        # Build lookup dict: field_name -> field_type (string)
        widgets_by_name = {w['field_name']: w['field_type'] for w in filtered_widgets}

        errors = []
        warnings = []
        incompatible_count = 0
        total_checked = 0

        # Check each field
        for field in schema.get("fields", []):
            pdf_name = field.get("pdf_field_name")
            if not pdf_name:
                continue

            widget_type = widgets_by_name.get(pdf_name)
            if not widget_type:
                continue

            schema_type = field.get("type")

            if not self._is_compatible(widget_type, schema_type):
                errors.append(
                    f"Type mismatch: {field.get('id')} - "
                    f"PDF widget is '{widget_type}', schema is '{schema_type}'"
                )
                incompatible_count += 1

            total_checked += 1

        # Check table columns
        for field in schema.get("fields", []):
            if field.get("type") != "table":
                continue

            for col in field.get("columns", []):
                pdf_name = col.get("pdf_field_name")
                if not pdf_name:
                    continue

                widget_type = widgets_by_name.get(pdf_name)
                if not widget_type:
                    continue

                schema_type = col.get("type")

                if not self._is_compatible(widget_type, schema_type):
                    errors.append(
                        f"Column type mismatch: {col.get('id')} - "
                        f"PDF widget is '{widget_type}', schema is '{schema_type}'"
                    )
                    incompatible_count += 1

                total_checked += 1

        # Check options (radio/checkbox groups)
        for field in schema.get("fields", []):
            for option in field.get("options", []):
                pdf_name = option.get("pdf_field_name")
                if not pdf_name:
                    continue

                widget_type = widgets_by_name.get(pdf_name)
                if not widget_type:
                    continue

                schema_type = field.get("type")  # parent field type

                if not self._is_compatible(widget_type, schema_type):
                    errors.append(
                        f"Option type mismatch: {option.get('label')} in {field.get('id')} - "
                        f"PDF widget is '{widget_type}', schema group is '{schema_type}'"
                    )
                    incompatible_count += 1

                total_checked += 1

        if total_checked == 0:
            return VerificationResult(
                layer="type_compatibility",
                passed=False,
                score=0.0,
                warnings=["No fields with pdf_field_name to check"]
            )

        compatibility_rate = 1.0 - (incompatible_count / total_checked)
        passed = incompatible_count == 0

        return VerificationResult(
            layer="type_compatibility",
            passed=passed,
            score=compatibility_rate,
            errors=errors,
            warnings=warnings,
            details={
                "total_checked": total_checked,
                "compatible": total_checked - incompatible_count,
                "incompatible": incompatible_count,
                "compatibility_percent": compatibility_rate * 100
            }
        )

    def verify_structural_consistency(self, schema: Dict[str, Any]) -> VerificationResult:
        """
        Verify internal consistency of schema structure.
        """
        errors = []
        warnings = []
        checks_passed = 0
        total_checks = 0

        # Check 1: Radio groups must have 2+ options
        for field in schema.get("fields", []):
            if field.get("type") == "radio" or field.get("group_kind") == "radio":
                total_checks += 1
                options = field.get("options", [])
                if len(options) < 2:
                    errors.append(f"Radio field {field.get('id')} has < 2 options")
                else:
                    checks_passed += 1

        # Check 2: Tables should have columns
        for field in schema.get("fields", []):
            if field.get("type") == "table":
                total_checks += 1
                columns = field.get("columns", [])
                if not columns:
                    errors.append(f"Table field {field.get('id')} has no columns")
                else:
                    checks_passed += 1

        # Check 3: show_if fields should exist
        all_field_ids = {f.get("id") for f in schema.get("fields", [])}
        for field in schema.get("fields", []):
            show_if = field.get("show_if")
            if show_if:
                total_checks += 1
                target_field = show_if.get("field")
                if target_field not in all_field_ids:
                    warnings.append(
                        f"Field {field.get('id')} show_if references non-existent field '{target_field}'"
                    )
                else:
                    checks_passed += 1

        # Check 4: No duplicate field IDs
        field_ids = [f.get("id") for f in schema.get("fields", []) if f.get("id")]
        duplicates = [fid for fid in set(field_ids) if field_ids.count(fid) > 1]
        if duplicates:
            total_checks += 1
            errors.append(f"Duplicate field IDs: {duplicates}")
        else:
            total_checks += 1
            checks_passed += 1

        # Check 5: All fields should have required attributes
        for field in schema.get("fields", []):
            total_checks += 1
            required_attrs = ["id", "name", "type"]
            missing = [attr for attr in required_attrs if not field.get(attr)]

            # Check for section (either section_id or section is acceptable)
            if not field.get("section_id") and not field.get("section"):
                missing.append("section_id or section")

            if missing:
                errors.append(f"Field {field.get('id', 'UNKNOWN')} missing attributes: {missing}")
            else:
                checks_passed += 1

        if total_checks == 0:
            total_checks = 1  # Avoid division by zero

        consistency_score = checks_passed / total_checks
        passed = len(errors) == 0

        return VerificationResult(
            layer="structural_consistency",
            passed=passed,
            score=consistency_score,
            errors=errors,
            warnings=warnings,
            details={
                "checks_run": total_checks,
                "checks_passed": checks_passed,
                "consistency_percent": consistency_score * 100
            }
        )

    def _normalize_pdf_field_name(self, full_name: str) -> str:
        """
        Normalize PDF field name by extracting the actual field name
        from the full hierarchy path.

        Example:
          'form1[0].#subform[0].PtAILine1_ANumber[0]' -> 'PtAILine1_ANumber[0]'
        """
        if not full_name:
            return full_name

        # Extract the last component after the last dot
        if '.' in full_name:
            return full_name.split('.')[-1]
        return full_name

    def _collect_pdf_field_names(self, field: Dict[str, Any], names: Set[str]):
        """Recursively collect all PDF field names from a field."""
        if field.get("pdf_field_name"):
            names.add(field["pdf_field_name"])

        # Check consolidated_widgets (our new tracking method)
        for widget_name in field.get("consolidated_widgets", []):
            names.add(widget_name)

        # Check columns
        for col in field.get("columns", []):
            if col.get("pdf_field_name"):
                names.add(col["pdf_field_name"])

        # Check options
        for opt in field.get("options", []):
            if opt.get("pdf_field_name"):
                names.add(opt["pdf_field_name"])

    def _normalize_widget_type(self, widget) -> str:
        """Normalize PDF widget type."""
        wtype = widget.field_type
        # PyMuPDF field types: TEXT=1, CHECKBOX=2, RADIO=3, SELECT=4, SIGNATURE=5
        type_map = {
            1: "text",
            2: "checkbox",
            3: "radio",
            4: "select",
            5: "signature",
        }
        return type_map.get(wtype, "unknown")

    def _is_compatible(self, widget_type: str, schema_type: str) -> bool:
        """Check if schema type is compatible with widget type."""
        if widget_type not in self.TYPE_COMPATIBILITY:
            return True  # Unknown widget type, assume OK

        compatible_types = self.TYPE_COMPATIBILITY[widget_type]
        return schema_type in compatible_types

    def save_report(self, report: VerificationReport, output_path: str):
        """Save verification report to JSON."""
        report_dict = {
            "overall_passed": report.overall_passed,
            "confidence_score": report.confidence_score,
            "summary": report.summary,
            "layers": [
                {
                    "layer": l.layer,
                    "passed": l.passed,
                    "score": l.score,
                    "errors": l.errors,
                    "warnings": l.warnings,
                    "details": l.details
                }
                for l in report.layers
            ]
        }

        with open(output_path, 'w') as f:
            json.dump(report_dict, f, indent=2)

        print(f"Verification report saved to: {output_path}")


# Convenience function
def verify_schema(pdf_path: str, schema_path: str, output_path: str = None) -> VerificationReport:
    """
    Verify a schema against its PDF.

    Args:
        pdf_path: Path to PDF file
        schema_path: Path to schema JSON file
        output_path: Optional path to save verification report

    Returns:
        VerificationReport

    Example:
        >>> report = verify_schema("form.pdf", "schema.json", "verification.json")
        >>> print(f"Passed: {report.overall_passed}, Confidence: {report.confidence_score}")
    """
    with open(schema_path) as f:
        schema = json.load(f)

    verifier = SchemaVerifier()
    report = verifier.verify(pdf_path, schema)

    if output_path:
        verifier.save_report(report, output_path)

    return report
