#!/usr/bin/env python3
import os
import sys
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# Add more common large or generated directories to skip
exclude_dirs = {'.venv', '__pycache__', '.git', 'node_modules', 'dist', 'frontend', 'Example PDFs'}
search_terms = ['genai.client', 'genai.configure']
matches = []
# Skip files larger than 1MB to avoid long reads
MAX_BYTES = 1_000_000
for dirpath, dirnames, filenames in os.walk(root):
    # mutate dirnames in-place to skip excluded dirs
    dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
    for fn in filenames:
        path = os.path.join(dirpath, fn)
        # skip binary or irrelevant files by extension
        if fn.endswith(('.pyc', '.pkl', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.whl', '.mp3', '.wav', '.pdf')):
            continue
        try:
            size = os.path.getsize(path)
            if size > MAX_BYTES:
                # skip very large files
                continue
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f, start=1):
                    for term in search_terms:
                        if term in line:  # case-sensitive
                            matches.append((path, i, term, line.rstrip('\n')))
        except (OSError, UnicodeDecodeError) as e:
            # skip files we can't read as text or access
            continue

if not matches:
    print('No case-sensitive matches for genai.client or genai.configure found.')
    sys.exit(0)

for p, ln, term, text in matches:
    print(f'{term} @ {p}:{ln}: {text}')

sys.exit(0)
