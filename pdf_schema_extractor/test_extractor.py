"""
Test script for the PDF Schema Extractor.
"""

import json
import os
from pdf_schema_extractor.extractor import extract_schema

def main():
    """Main function to run the extractor and print the output."""
    # Get the absolute path to the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Correct the path to the PDF file
    pdf_file_path = os.path.join(project_root, "example_pdfs/i-589/i-589-asylum-application.pdf")
    output_schema_path = os.path.join(project_root, "outputs/i589_extracted_schema.json")
    
    print(f"Extracting schema from {pdf_file_path}...")
    if not os.path.exists(pdf_file_path):
        print(f"FATAL: PDF file not found at {pdf_file_path}")
        return

    schema_data = extract_schema(pdf_file_path)

    # Use Pydantic's model_dump_json for proper serialization
    json_output = schema_data.model_dump_json(indent=2)
    
    with open(output_schema_path, "w") as f:
        f.write(json_output)
        
    print(f"Schema extracted and saved to {output_schema_path}")

if __name__ == "__main__":
    main()
