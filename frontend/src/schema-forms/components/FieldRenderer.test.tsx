/**
 * Unit tests for FieldRenderer routing.
 * Pins that a v2 `checkbox_group` field routes to CheckboxField's group UI
 * rather than falling through to the "Unknown field type" default (Codex PR
 * #346): migrated kits (i-90 race, W-7-2 document type) carry checkbox_group,
 * and without the route those fields are unfillable.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { FieldRenderer } from './FieldRenderer';
import type { FormField } from '../types/schema';

describe('FieldRenderer: checkbox_group routing', () => {
  afterEach(() => cleanup());

  const group: FormField = {
    id: 'race',
    name: 'Race',
    spoken_name: 'race',
    type: 'checkbox_group',
    section_id: 's',
    options: [
      { value: 'white', label: 'White' },
      { value: 'asian', label: 'Asian' },
    ],
  };

  it('renders a checkbox_group through CheckboxField (its option checkboxes), not the Unknown-type fallback', () => {
    render(<FieldRenderer field={group} value={[]} onChange={vi.fn()} />);
    // The group's option labels render (CheckboxField group UI)...
    expect(screen.getByLabelText('White')).toBeTruthy();
    expect(screen.getByLabelText('Asian')).toBeTruthy();
    // ...and the "Unknown field type" fallback does NOT.
    expect(screen.queryByText(/Unknown field type/)).toBeNull();
  });
});
