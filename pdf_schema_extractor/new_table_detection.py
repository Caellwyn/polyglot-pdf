"""
New table detection algorithm based on forensic analysis of PDF patterns.

Pattern A: Numbered field names (Child1, Child2) - number indicates logical table row
Pattern B: Array indices (TextField13[0], TextField13[6]) - spatial + index grouping
"""

from collections import defaultdict, Counter
import re


def detect_table_patterns_v2(fields):
    """
    Detect repeating field patterns that indicate table structures.

    Strategy:
    - Pattern A: Numbered field names (Child1, Child2) - number indicates logical table row
      One logical row can span multiple physical PDF rows at different Y positions.
    - Pattern B: Array indices (TextField13[0], TextField13[6]) - spatial + index grouping

    Returns list of table groups (each group is a list of row lists).
    """
    # Group fields by section
    section_fields = defaultdict(list)
    for field in fields:
        section_fields[field.section_id].append(field)

    table_groups = []
    non_repeating_fields = []

    for section_id, fields_list in section_fields.items():
        # Track which fields have been added to tables
        used_field_ids = set()

        # PATTERN A: Numbered field names (e.g., Child1, Child2, Entry1, Entry2)
        # Key insight: The NUMBER indicates the logical table row, not the Y position!

        # Step 1: Extract base name and row number from field names
        numbered_fields = defaultdict(lambda: defaultdict(list))  # {base_name: {row_num: [fields]}}

        for field in fields_list:
            if not hasattr(field, 'pdf_field_name') or not field.pdf_field_name:
                continue

            pdf_name = field.pdf_field_name.split('.')[-1]
            pdf_name_no_idx = pdf_name.split('[')[0]

            # Match pattern like: ChildAlien1, Entry2, Address3
            # Require at least 2 letters before the number to avoid false matches
            match = re.match(r'^([A-Za-z_]{2,}?)(\d+)$', pdf_name_no_idx)

            if match:
                base_name = match.group(1)
                row_num = int(match.group(2))
                numbered_fields[base_name][row_num].append(field)

        # Step 2: Find groups of base names that share the same row numbers (same table)
        # Group bases by their row number sets
        row_nums_to_bases = defaultdict(dict)  # {frozenset(row_nums): {base_name: rows_dict}}

        for base_name, rows_dict in numbered_fields.items():
            if len(rows_dict) >= 2:  # At least 2 rows
                row_nums_set = frozenset(rows_dict.keys())
                row_nums_to_bases[row_nums_set][base_name] = rows_dict

        # Step 3: Create tables from grouped base names
        for row_nums_set, bases_dict in row_nums_to_bases.items():
            if len(bases_dict) >= 3:  # At least 3 different field name patterns
                row_nums_sorted = sorted(list(row_nums_set))

                # Build table rows
                table_rows = []
                for row_num in row_nums_sorted:
                    # Collect all fields for this logical row number from all bases
                    row_fields = []
                    for base_name in sorted(bases_dict.keys()):
                        if row_num in bases_dict[base_name]:
                            row_fields.extend(bases_dict[base_name][row_num])

                    if row_fields:
                        # Sort by X position to get column order
                        row_fields_sorted = sorted(row_fields, key=lambda f: f.pdf_position.x if hasattr(f, 'pdf_position') else 0)
                        table_rows.append(row_fields_sorted)

                        # Mark as used
                        for f in row_fields_sorted:
                            used_field_ids.add(f.id)

                if table_rows and len(table_rows) >= 2:
                    table_groups.append((section_id, table_rows))

        # PATTERN B: Array indices (e.g., TextField13[0], TextField13[1], TextField13[2])
        # Extract fields with array indices that weren't used in Pattern A
        array_fields = []
        for field in fields_list:
            if field.id in used_field_ids:
                continue

            if not hasattr(field, 'pdf_field_name') or not field.pdf_field_name:
                continue

            pdf_name = field.pdf_field_name.split('.')[-1]
            match = re.match(r'^(.+?)\[(\d+)\]$', pdf_name)

            if match:
                base_name = match.group(1)
                array_idx = int(match.group(2))
                array_fields.append({
                    'field': field,
                    'base_name': base_name,
                    'array_idx': array_idx,
                    'y': field.pdf_position.y if hasattr(field, 'pdf_position') else 0,
                    'x': field.pdf_position.x if hasattr(field, 'pdf_position') else 0,
                })

        # Group array fields by spatial regions (Y gaps > 100px indicate different tables)
        if array_fields:
            # Sort by Y position
            array_fields.sort(key=lambda item: item['y'])

            # Split into spatial groups based on Y gaps
            spatial_groups = []
            current_group = []
            prev_y = None

            for item in array_fields:
                if prev_y is not None and (item['y'] - prev_y) > 100:
                    # Large gap - new spatial group
                    if current_group:
                        spatial_groups.append(current_group)
                    current_group = [item]
                else:
                    current_group.append(item)
                prev_y = item['y']

            if current_group:
                spatial_groups.append(current_group)

            # Process each spatial group
            for group_items in spatial_groups:
                table_rows = _process_array_index_group(group_items)
                if table_rows and len(table_rows) >= 2:
                    table_groups.append((section_id, table_rows))
                    for row in table_rows:
                        for f in row:
                            used_field_ids.add(f.id)

        # Add unused fields to non-repeating list
        for field in fields_list:
            if field.id not in used_field_ids:
                non_repeating_fields.append(field)

    return table_groups, non_repeating_fields


def _process_array_index_group(items):
    """
    Helper function to process array index pattern into table rows within a spatial group.
    Groups fields at same Y position, uses array indices to identify row numbers.
    """
    # Group by Y position (physical rows)
    y_groups = defaultdict(list)
    for item in items:
        y_key = round(item['y'] / 20) * 20
        y_groups[y_key].append(item)

    # For each physical row (Y position), determine which logical row it belongs to
    # by finding the most common array index
    y_to_row_idx = {}
    for y_key, y_items in y_groups.items():
        indices = [item['array_idx'] for item in y_items]
        if indices:
            # Use most common index as the row identifier
            most_common_idx = Counter(indices).most_common(1)[0][0]
            y_to_row_idx[y_key] = most_common_idx

    # Group fields by logical row index
    row_fields_dict = defaultdict(list)
    for item in items:
        y_key = round(item['y'] / 20) * 20
        row_idx = y_to_row_idx.get(y_key)
        if row_idx is not None:
            row_fields_dict[row_idx].append(item['field'])

    # Build table rows sorted by row index
    table_rows = []
    for row_idx in sorted(row_fields_dict.keys()):
        row_fields = row_fields_dict[row_idx]
        if len(row_fields) >= 2:  # Need at least 2 columns
            # Sort by X position to get column order
            row_fields_sorted = sorted(row_fields, key=lambda f: f.pdf_position.x if hasattr(f, 'pdf_position') else 0)
            table_rows.append(row_fields_sorted)

    return table_rows
