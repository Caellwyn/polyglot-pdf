#!/usr/bin/env python3
"""
Fix the adult_intake_demo_schema.json to match the FormSchema contract.

Current format:
{
  "form_fields": [
    {"id": "...", "field_type": "text", ...}
  ]
}

Expected format (FormSchema):
{
  "source": "web",
  "form_metadata": {
    "title": "...",
    "url": "..."
  },
  "fields": [
    {"id": "...", "type": "text", ...}
  ]
}

Changes needed:
1. Add "source" and "form_metadata" at root
2. Rename "form_fields" → "fields"
3. Rename "field_type" → "type" in each field
4. Keep all other field properties (spoken_name, spoken_aliases, section_id, etc.)
"""

import json
from pathlib import Path

# Load the current schema
schema_path = Path(__file__).parent.parent / "demos" / "adult_intake_demo_schema.json"
with open(schema_path, "r", encoding="utf-8") as f:
    old_schema = json.load(f)

# Transform to match FormSchema contract
new_schema = {
    "source": "web",
    "form_metadata": {
        "title": "Ellie Mental Health Adult Intake Form",
        "url": "https://demo.yourdomain.com/adult-intake"  # Will be updated at runtime
    },
    "fields": []
}

# Transform each field
for field in old_schema["form_fields"]:
    # Rename field_type → type
    new_field = {**field}
    if "field_type" in new_field:
        new_field["type"] = new_field.pop("field_type")
    
    new_schema["fields"].append(new_field)

# Save the fixed schema
with open(schema_path, "w", encoding="utf-8") as f:
    json.dump(new_schema, f, indent=2, ensure_ascii=False)

print(f"✓ Fixed schema: {len(new_schema['fields'])} fields")
print(f"  Saved to: {schema_path}")
