#!/usr/bin/env python3
"""Analyze section breakdown in the demo schema."""

import json
from collections import defaultdict, OrderedDict

# Load schema
with open('demos/adult_intake_demo_schema.json', 'r', encoding='utf-8') as f:
    schema = json.load(f)

# Analyze sections
sections = OrderedDict()
field_index = 0

for field in schema['fields']:
    sid = field['section_id']
    
    if sid not in sections:
        sections[sid] = {
            'label': field['section_label'],
            'fields': [],
            'groups': defaultdict(list)
        }
    
    sections[sid]['fields'].append({
        'index': field_index,
        'id': field['id'],
        'spoken': field['spoken_name'],
        'group_id': field.get('group_id'),
        'type': field['type']
    })
    
    if field.get('group_id'):
        sections[sid]['groups'][field['group_id']].append(field['id'])
    
    field_index += 1

# Print analysis
print("=== CURRENT SECTION BREAKDOWN ===\n")
print(f"Total fields: {field_index}\n")

for sid, data in sections.items():
    print(f"{sid}")
    print(f"  Label: {data['label']}")
    print(f"  Fields: {len(data['fields'])}")
    
    if data['groups']:
        print(f"  Groups: {len(data['groups'])}")
        for gid, field_ids in data['groups'].items():
            print(f"    - {gid}: {len(field_ids)} fields")
    print()
