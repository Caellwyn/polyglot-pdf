// @vitest-environment jsdom
//
// Regression test for bd polyglot-pdf-jzvs: LanguageSelectionModal used to fetch
// GET /api/form-kits itself with NO static fallback, so in backend-less local dev
// it showed "Unable to load available forms" even though the parent's static
// /form-kits/index.json fetch had already succeeded. The fix makes the modal
// purely presentational: the parent (SchemaFormDemo) resolves the form list and
// passes it in as the `forms` prop; the modal never fetches.
//
// These tests lock in that contract:
//   1. The modal renders the language step immediately, with NO network call,
//      even when there is no backend (global.fetch would reject).
//   2. It never renders the old "Unable to load available forms" error state.
//   3. The forms passed in as a prop drive the form-selection step's cards.
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { LanguageSelectionModal } from './LanguageSelectionModal'
import type { FormKitDescriptor } from '../types/formKit'

const FORMS: FormKitDescriptor[] = [
  {
    id: 'i-90',
    label: 'I-90 (Green Card Replacement)',
    description: 'USCIS Form I-90',
    schemaFile: 'schema.json',
    schemaPath: '/form-kits/i-90/schema.json',
    pdfFile: 'form.pdf',
    pdfPath: '/form-kits/i-90/form.pdf',
  },
  {
    id: 'w7',
    label: 'W7',
    schemaFile: 'schema.json',
    schemaPath: '/form-kits/w7/schema.json',
    pdfFile: 'form.pdf',
    pdfPath: '/form-kits/w7/form.pdf',
  },
]

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('LanguageSelectionModal (bd polyglot-pdf-jzvs)', () => {
  it('renders the language step with no fetch, even with a dead backend', () => {
    // Fail loudly if the modal tries to fetch anything: the whole point of the
    // fix is that it no longer does its own /api/form-kits request.
    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockRejectedValue(new Error('ECONNREFUSED'))

    render(<LanguageSelectionModal forms={FORMS} onSelection={vi.fn()} />)

    // Language step is shown synchronously (no loading spinner, no async gate).
    expect(
      screen.getByText(/Select Language \/ Seleccione Idioma/i)
    ).toBeTruthy()
    // The removed error state must never appear.
    expect(screen.queryByText(/Unable to load available forms/i)).toBeNull()
    // No network call at all.
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('drives the form-selection step from the forms prop', () => {
    const onSelection = vi.fn()
    render(<LanguageSelectionModal forms={FORMS} onSelection={onSelection} />)

    // Pick a language -> with no preselected form, advance to form selection.
    // Use Spanish: its English name ("Spanish") is distinct from its native
    // name ("Espanol"), so getByText matches exactly one card. (English's name
    // and nativeName are identical, which would match two nodes.)
    fireEvent.click(screen.getByText('Spanish'))

    // Both forms passed in as props render as selectable cards.
    expect(screen.getByText('I-90 (Green Card Replacement)')).toBeTruthy()
    expect(screen.getByText('W7')).toBeTruthy()

    // Choosing a form completes the selection with (formId, language).
    fireEvent.click(screen.getByText('W7'))
    expect(onSelection).toHaveBeenCalledWith('w7', 'Spanish')
  })

  it('completes on language alone when a form is preselected (VoiceOverlay path)', () => {
    // The VoiceOverlay callers pass preselectedFormId and no forms; the
    // form-selection step is unreachable, so the empty default is fine.
    const onSelection = vi.fn()
    render(
      <LanguageSelectionModal onSelection={onSelection} preselectedFormId="i-90" />
    )

    fireEvent.click(screen.getByText('Spanish'))
    expect(onSelection).toHaveBeenCalledWith('i-90', 'Spanish')
  })
})
