"""Compatibility shim: the recovered extractor imports `.models`, but the schema
models were recovered as `form_models.py` (their name at commit a0bf111). Re-export
everything so `from .models import ...` resolves without editing every call site.

Throwaway research scaffold for the bake-off (bd polyglot-pdf-7a9.4).
ASCII-only.
"""
from .form_models import *  # noqa: F401,F403
from .form_models import (  # noqa: F401  explicit re-export of the names extractor.py needs
    FormSchema,
    FormField,
    PDFPosition,
    FormMetadata,
    ExtractionInfo,
    FormSource,
    FieldType,
    FormSection,
    FormPart,
    FormSupplement,
    FieldOption,
    GroupKind,
    ValidationRules,
    FieldHelp,
    ConditionalDisplay,
    ConditionalOperator,
    TableColumn,
    MultiEntryConfig,
    SupplementType,
)
