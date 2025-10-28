"""
Test script to run the PDF schema extractor and compare results.
"""

import sys
import json
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pdf_schema_extractor.extractor import extract_schema

if __name__ == "__main__":
    pdf_file_path = r"C:\Users\caell\OneDrive\AILearning\polyglot-pdf\example_pdfs\i-589\i-589-asylum-application.pdf"
    output_schema_path = r"C:\Users\caell\OneDrive\AILearning\polyglot-pdf\pdf_schema_extractor\test_schemas\extracted_schema.json"
    
    print(f"Extracting schema from {pdf_file_path}...")
    schema_data = extract_schema(pdf_file_path)
    
    # Convert to dict for JSON serialization
    schema_dict = schema_data.model_dump(exclude_none=True)
    
    with open(output_schema_path, "w") as f:
        json.dump(schema_dict, f, indent=2)
        
    print(f"Schema extracted and saved to {output_schema_path}")
    print(f"Total fields extracted: {len(schema_data.fields)}")
    print(f"Total sections: {len(schema_data.sections)}")
    if schema_data.parts:
        print(f"Total parts: {len(schema_data.parts)}")
    if schema_data.supplements:
        print(f"Total supplements: {len(schema_data.supplements)}")
