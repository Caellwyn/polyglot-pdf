#!/usr/bin/env python3
"""Test if short field names are unique and safe to use."""

import fitz
from collections import Counter

doc = fitz.open('test_schemas/test_pdfs/i-589.pdf')

# Extract all widgets
all_widgets = []
for page in doc:
    all_widgets.extend(list(page.widgets()))

# Get short names
short_names = [w.field_name.split('.')[-1] for w in all_widgets]

# Check uniqueness
counts = Counter(short_names)
duplicates = {name: count for name, count in counts.items() if count > 1}

print(f'Total widgets: {len(all_widgets)}')
print(f'Unique short names: {len(set(short_names))}')
print(f'Duplicates: {len(duplicates)}')

if duplicates:
    print('\nDuplicate short names (showing all):')
    for name, count in sorted(duplicates.items(), key=lambda x: x[1], reverse=True):
        print(f'  {name}: {count} occurrences')
        # Show the full names for this duplicate
        full_names = [w.field_name for w in all_widgets if w.field_name.split('.')[-1] == name]
        for fn in full_names[:3]:  # Show first 3
            print(f'    -> {fn}')
else:
    print('\n✓ All short names are unique - safe to use!')
    print('\nSample mappings:')
    for w in all_widgets[:5]:
        short = w.field_name.split('.')[-1]
        print(f'  {short} <- {w.field_name}')
