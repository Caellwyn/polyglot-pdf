# PDF Schema Extractor

Extracts structured schemas from government PDF forms to power voice AI for non-English speaking immigrants.

---

## Quick Start

### Extract Schema from PDF

```bash
# 1. Extract widgets
python widget_inventory.py test_schemas/test_pdfs/i-589.pdf

# 2. Create annotated PDF
python pdf_annotator.py test_schemas/test_pdfs/i-589.pdf

# 3. Extract groupings with Gemini
python gemini_grouping_extractor.py test_schemas/test_pdfs/i-589.pdf

# 4. Parse hierarchy from tooltips
python heuristic_hierarchy_parser.py test_schemas/test_pdfs/i-589.pdf

# 5. Build complete schema
python schema_builder_from_groupings.py test_schemas/test_pdfs/i-589.pdf gemini_groupings.json

# 6. Verify schema quality
python -c "from schema_verifier import verify_schema; verify_schema('test_schemas/test_pdfs/i-589.pdf', 'final_schema.json')"
```

### Current Best Schema

**Use this:** `final_schema_minimal.json`
- 99.9% verification score
- 100% widget coverage (405/405 fields)
- 303 total fields
- Cost: ~$0.02-0.05 per form

---

## Active Files (Production)

### Core Pipeline
- `widget_inventory.py` - Extract widgets from PDF
- `pdf_annotator.py` - Create labeled PDF for Gemini
- `gemini_grouping_extractor.py` - Extract semantic groups/tables
- `heuristic_hierarchy_parser.py` - Parse tooltip hierarchy
- `schema_builder_from_groupings.py` - Build complete schema

### Validation
- `schema_verifier.py` - Multi-layer verification (FIXED)

### Documentation
- `PROJECT_STATUS.md` - **READ THIS FIRST** - Complete project status
- `METRICS_AUDIT.md` - Documents verifier issues and fixes
- `VERIFIER_FINAL_RESULTS.md` - Latest verification results
- `MINIMAL_APPROACH_SUMMARY.md` - Minimal approach details
- `LABEL_OVERLAY_FINDINGS.md` - Why label overlay doesn't help

---

## Archived Files

### archive/hybrid_v2/
Old batched Gemini extraction approach (replaced by minimal approach)
- Cost: 9 API calls vs 1-2
- Quality: 70.9% vs 99.9%
- **Don't use these files**

### archive/documentation/
Old strategy docs (superseded by PROJECT_STATUS.md)

---

## Known Issues & Limitations

### Missing Features (CRITICAL for production)
1. **Conditional logic (0%)** - No "show_if" rules extracted
2. **Validation rules (0%)** - No constraints/formats captured
3. **Round-trip testing (0%)** - Haven't verified schema→PDF works
4. **Section accuracy (83%)** - 17% of fields mislabeled

### See PROJECT_STATUS.md for:
- Complete gap analysis
- Prioritized next steps
- Quality metrics
- Production readiness checklist

---

## Quality Metrics

### Current (Minimal Approach)
- Widget Coverage: **100%** (405/405)
- Type Compatibility: **100%**
- Structural Consistency: **99.7%**
- Overall Confidence: **99.9%**

### Target for Production
- Round-trip: **100%** (not tested yet)
- Conditional logic: **100%** (0% currently)
- Validation rules: **95%+** (0% currently)
- Section accuracy: **100%** (83% currently)

---

## Key Decisions

**Approach:** Minimal (Gemini for semantics, Python for precision)
- ✅ Cheaper (75% cost reduction)
- ✅ Better quality (99.9% vs 70.9%)
- ✅ No truncation issues
- ✅ Guaranteed 100% coverage

**Architecture:** Separation of concerns works
- Gemini: Semantic grouping, table detection
- Python: Pattern matching, completeness guarantees
- Human: Review edge cases only

---

## Next Steps

1. **Round-trip testing** - CRITICAL BLOCKER
2. **Conditional logic extraction** - CRITICAL for voice AI
3. **Validation rules** - CRITICAL for data quality
4. **Fix section parsing** - Improve from 83% to 100%

See PROJECT_STATUS.md for detailed roadmap.

---

## Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Set Gemini API key
export GEMINI_API_KEY="your-key-here"
```

---

## Support

For questions or issues, refer to:
1. `PROJECT_STATUS.md` - Comprehensive project status
2. Archived docs - Historical context
3. Code comments - Implementation details
