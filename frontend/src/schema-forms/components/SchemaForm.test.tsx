// @vitest-environment jsdom
//
// SchemaForm structural invariants (bd polyglot-pdf-fdz8).
//
// This pins the JSX invariant that the voice overlay (VoiceOverlay /
// VoiceOverlayMobile) and its ConnectionManager live OUTSIDE the switched
// view container -- they are siblings of the Simplified/Preview ternary, not
// children of either branch. If a future refactor nested the overlay inside
// the `viewMode === 'preview' ? <PreviewPane/> : <form/>` ternary, toggling
// the view would UNMOUNT and remount the overlay, which restarts the Gemini
// session (the overlay's mount-time connect). No existing test caught that:
// the whole suite would stay green while the session silently reset on every
// toggle. The identity assertion below is the one that goes red.
//
// The heavy children (both overlays, the lazy PreviewPane/FilledPreviewModal,
// auth, the connection manager, the mic stream) are mocked to stubs so the
// test exercises only SchemaForm's own render structure.

import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { FormSchema } from '../types/schema';

// --- Mocks for SchemaForm's heavy dependencies -----------------------------

// Report the test-harness path ON so SchemaForm SKIPS its mount-time
// getUserMedia (jsdom has no navigator.mediaDevices) and marks the stream ready
// immediately -- the connection manager then gets created and the overlay
// renders, with no mic touched. (This flag ONLY gates the mic-skip in
// SchemaForm; it does not change the view-mode structure under test.)
vi.mock('../../shared/config', () => ({
  isTestHarnessEnabled: () => true,
}));

// A no-op connection manager so SchemaForm's stream-ready effect can create one
// and render the overlay. Only the methods SchemaForm calls need to exist.
// We ALSO capture the onNextField callback SchemaForm passes in (5th arg): the
// continuous-mode section-paging test drives it directly to simulate the voice
// model advancing its focus to a field in another section.
let capturedOnNextField: ((fieldId: string | null) => void) | null = null;
vi.mock('../../shared/connection', () => ({
  createConnectionManager: vi.fn(
    (
      _schema: unknown,
      _onStatus: unknown,
      _lang: unknown,
      _stream: unknown,
      onNextField: (fieldId: string | null) => void,
    ) => {
      capturedOnNextField = onNextField;
      return { connect: vi.fn(), disconnect: vi.fn() };
    },
  ),
}));

vi.mock('../../shared/audioConstraints', () => ({
  MIC_AUDIO_CONSTRAINTS: {},
}));

// Auth: a logged-out user is fine (getToken path is never exercised by the stub
// connection manager).
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));

// The overlays -- stub each to a single identifiable node. The desktop overlay
// carries a data-testid we can grab and compare across a toggle.
vi.mock('../../demo/VoiceOverlay', () => ({
  VoiceOverlay: () => <div data-testid="voice-overlay">overlay</div>,
}));
vi.mock('../../demo/VoiceOverlayMobile', () => ({
  VoiceOverlayMobile: () => <div data-testid="voice-overlay-mobile">overlay-mobile</div>,
}));

// The lazy Preview surfaces -- stub so the Preview branch renders synchronously
// (no pdfjs, no Suspense fallback churn).
vi.mock('../../pdf-view/PreviewPane', () => ({
  default: () => <div data-testid="preview-pane">preview</div>,
}));
vi.mock('../../pdf-view/FilledPreviewModal', () => ({
  default: () => <div data-testid="filled-preview-modal">modal</div>,
}));

import { SchemaForm } from './SchemaForm';
import { SchemaFormStateManager } from '../state/schemaFormState';

// --- A minimal valid schema ------------------------------------------------

function makeSchema(): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Test Form',
      version: '1.0',
      language: 'en',
      form_number: 'TEST-1',
    },
    sections: [
      { id: 'sec1', label: 'Section One', order: 1, fields: ['f1'] },
    ],
    fields: [
      {
        id: 'f1',
        name: 'Field One',
        spoken_name: 'field one',
        section_id: 'sec1',
        type: 'text',
      } as any,
    ],
  };
}

// A two-section schema for the continuous-mode paging test: the voice model can
// advance focus from a field in sec1 to a field in sec2, and the simplified view
// must page to sec2.
function makeTwoSectionSchema(): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'Two Section Form',
      version: '1.0',
      language: 'en',
      form_number: 'TEST-2',
    },
    sections: [
      { id: 'sec1', label: 'Section One', order: 1, fields: ['f1'] },
      { id: 'sec2', label: 'Section Two', order: 2, fields: ['f2'] },
    ],
    fields: [
      { id: 'f1', name: 'Field One', spoken_name: 'field one', section_id: 'sec1', type: 'text' } as any,
      { id: 'f2', name: 'Field Two', spoken_name: 'field two', section_id: 'sec2', type: 'text' } as any,
    ],
  };
}

// SchemaForm reads window.innerWidth at mount (initialViewMode) and on resize.
// Force a stable DESKTOP width so mounts start Simplified only because nothing
// is stored (not because of a mobile-width override), and so the overlay picks
// the desktop VoiceOverlay stub.
function setWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  });
}

describe('SchemaForm view-mode structure (bd polyglot-pdf-fdz8)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    setWidth(1280);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // Post-cutover (bd polyglot-pdf-v437): the toggle is unconditional -- no
  // query param or sessionStorage opt-in gates it any more.
  it('renders the Simplified/Preview toggle unconditionally', async () => {
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    // Let the stream-ready + connection-manager effects settle.
    await act(async () => {});
    expect(screen.getByRole('tablist', { name: 'Form view' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Simplified' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Preview' })).toBeTruthy();
  });

  it('still starts in Simplified when nothing is stored (cutover did NOT change the landing view)', async () => {
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    await act(async () => {});
    expect(screen.getByRole('tab', { name: 'Simplified' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: 'Preview' }).getAttribute('aria-selected')).toBe('false');
  });

  // The OTHER direction of the stored-preference contract: at desktop width a
  // stored 'preview' must actually be HONORED at mount. Without this, the
  // getStoredViewMode() read in SchemaForm's viewMode initialiser could be
  // deleted outright (passing null) and every other test would still pass --
  // viewMode.test.ts only covers the pure helper, and every other SchemaForm
  // test either clears storage or expects the mobile demotion.
  it('honors a stored preview choice at desktop width', async () => {
    sessionStorage.setItem('preview_view_mode', 'preview');
    setWidth(1280);
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    await act(async () => {});

    expect(screen.getByRole('tab', { name: 'Preview' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: 'Simplified' }).getAttribute('aria-selected')).toBe('false');
  });

  // A mobile-width mount demotes a stored 'preview' choice to Simplified (epic
  // rubric #5). It must PERSIST that demotion, like the resize path does --
  // otherwise state and storage disagree and the stale 'preview' silently
  // resurrects the next time this session is opened at desktop width. Reachable
  // only since the cutover (bd polyglot-pdf-v437) made the toggle tappable on
  // mobile at all.
  it('persists the mobile-width demotion instead of leaving a stale stored preview', async () => {
    sessionStorage.setItem('preview_view_mode', 'preview');
    setWidth(390);
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    await act(async () => {});

    expect(screen.getByRole('tab', { name: 'Simplified' }).getAttribute('aria-selected')).toBe('true');
    // The stored value must agree with what is actually shown.
    expect(sessionStorage.getItem('preview_view_mode')).toBe('simplified');
  });

  it('keeps the voice overlay mounted (same DOM node) across a Simplified->Preview toggle', async () => {
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    // The connection manager is created only once the (mocked) stream is ready;
    // flush the effects so the overlay renders.
    await act(async () => {});

    // Fresh mount at desktop width with nothing stored -> Simplified, and the
    // overlay is present as a sibling of the form container.
    expect(screen.getByText('Test Form')).toBeTruthy(); // the Simplified <form> header
    const overlayBefore = screen.getByTestId('voice-overlay');
    expect(overlayBefore).toBeTruthy();

    // Toggle to Preview.
    await act(async () => {
      fireEvent.click(screen.getByRole('tab', { name: 'Preview' }));
    });

    // The Preview branch is now showing (Simplified form header gone, preview
    // pane present) -- proving the switched container actually flipped.
    expect(screen.queryByText('Test Form')).toBeNull();
    expect(screen.getByTestId('preview-pane')).toBeTruthy();

    // THE INVARIANT: the overlay node survived the switch as the SAME element.
    // If the overlay were nested inside the view-switch ternary, flipping the
    // branch would remount it and this identity check would fail (a new node).
    const overlayAfter = screen.getByTestId('voice-overlay');
    expect(overlayAfter).toBe(overlayBefore);
  });

  it('resets Preview to Simplified when a live same-tab resize crosses into mobile width (bd polyglot-pdf-ipin)', async () => {
    vi.useFakeTimers();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      // Flush the mount effects (stream-ready, connection manager, overlay).
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      // Switch to Preview at desktop width.
      act(() => {
        fireEvent.click(screen.getByRole('tab', { name: 'Preview' }));
      });
      expect(screen.getByTestId('preview-pane')).toBeTruthy();
      expect(screen.queryByText('Test Form')).toBeNull();

      // Shrink the SAME tab into mobile width and fire the resize the app
      // listens for (the P1.1 resize-testing technique: defineProperty on
      // innerWidth + dispatch a 'resize' Event). The handler is debounced 250ms.
      act(() => {
        setWidth(390);
        window.dispatchEvent(new Event('resize'));
        vi.advanceTimersByTime(300);
      });

      // The view fell back to Simplified: the form header is back and the
      // Preview pane is gone -- the mobile-defaults-Simplified intent now holds
      // for a live resize, not only a fresh mount.
      expect(screen.getByText('Test Form')).toBeTruthy();
      expect(screen.queryByTestId('preview-pane')).toBeNull();
      expect(screen.getByRole('tab', { name: 'Simplified' }).getAttribute('aria-selected')).toBe('true');
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT drop Preview in the dead-zone band, so the view never mismatches the overlay (bd polyglot-pdf-ipin, fresh-eyes)', async () => {
    // The view-mode reset is keyed on the SAME mobile classification that picks
    // the overlay (dead-zone hysteresis: isMobile flips only at <=700), NOT an
    // independent 768 threshold. So a desktop->intermediate resize that lands in
    // the (700, 768] dead zone must keep BOTH Preview AND the desktop overlay --
    // never a "mobile-defaulted Simplified form + desktop overlay" mismatch.
    vi.useFakeTimers();
    try {
      render(<SchemaForm schema={makeSchema()} kitId="test" />);
      await act(async () => {
        vi.runOnlyPendingTimers();
      });

      act(() => {
        fireEvent.click(screen.getByRole('tab', { name: 'Preview' }));
      });
      expect(screen.getByTestId('preview-pane')).toBeTruthy();
      // Desktop overlay is showing at the 1280px mount width.
      expect(screen.getByTestId('voice-overlay')).toBeTruthy();
      expect(screen.queryByTestId('voice-overlay-mobile')).toBeNull();

      // Resize into the dead zone (750px is in (700, 820), and is > the 768
      // breakpoint the OLD flat-threshold code would have reset on).
      act(() => {
        setWidth(750);
        window.dispatchEvent(new Event('resize'));
        vi.advanceTimersByTime(300);
      });

      // Preview is KEPT (no mobile-default reset), and the overlay is STILL the
      // desktop one -- the two agree. This is the consistency the fresh-eyes
      // finding required; the old flat-768 reset would have flipped to Simplified
      // here while the overlay stayed desktop.
      expect(screen.getByTestId('preview-pane')).toBeTruthy();
      expect(screen.getByRole('tab', { name: 'Preview' }).getAttribute('aria-selected')).toBe('true');
      expect(screen.getByTestId('voice-overlay')).toBeTruthy();
      expect(screen.queryByTestId('voice-overlay-mobile')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

// ============================================================================
// Continuous-mode section paging (bd polyglot-pdf-gz20)
//
// The voice model fills across the whole form in ONE continuous session, but
// the simplified view still renders one section at a time and currentSectionId
// stays pinned to the first section. When the model's focus (onNextField) lands
// on a field in a later section, the simplified view must PAGE to that field's
// section -- otherwise the field is never rendered and the view is stranded on
// section 1 (the reported bug: "not changing sections visually").
// ============================================================================
describe('SchemaForm continuous-mode section paging (bd polyglot-pdf-gz20)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    capturedOnNextField = null;
    // This is about the simplified <form> view: the cleared sessionStorage
    // above means no stored view-mode choice, so the mount starts Simplified.
    setWidth(1280);
    // jsdom does not implement scrollIntoView; handleNextField's focus step
    // calls it on the located element. Stub it so the focus path is exercised
    // without throwing (we assert the section render, not the scroll itself).
    (Element.prototype as any).scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // Seed sessionStorage with a continuous-mode state for the given schema so the
  // component mounts already in continuous mode (in production this flag is set
  // during the handshake, which the stubbed connection manager never runs).
  function seedContinuousState(schema: FormSchema) {
    let s = SchemaFormStateManager.init(schema);
    s = SchemaFormStateManager.setContinuousSession(s, true);
    return s;
  }

  it('pages the simplified view to the section of the model-focused field', async () => {
    const schema = makeTwoSectionSchema();
    seedContinuousState(schema);

    render(<SchemaForm schema={schema} kitId="test" />);
    // Flush stream-ready + connection-manager effects so onNextField is captured.
    await act(async () => {});

    // Mount shows section 1 (currentSectionId pinned to the first section).
    expect(screen.getByText('Section One')).toBeTruthy();
    expect(screen.queryByText('Section Two')).toBeNull();
    expect(capturedOnNextField).toBeTruthy();

    // The voice model advances its focus to f2, which lives in section 2.
    await act(async () => {
      capturedOnNextField!('f2');
    });

    // The simplified view paged to section 2 -- f2 now renders, section 1 is gone.
    expect(screen.getByText('Section Two')).toBeTruthy();
    expect(screen.queryByText('Section One')).toBeNull();
  });

  it('does not page when the focused field is already in the shown section', async () => {
    const schema = makeTwoSectionSchema();
    seedContinuousState(schema);

    render(<SchemaForm schema={schema} kitId="test" />);
    await act(async () => {});

    expect(screen.getByText('Section One')).toBeTruthy();

    // Focus stays on f1 (already in the shown section) -> no section change.
    await act(async () => {
      capturedOnNextField!('f1');
    });

    expect(screen.getByText('Section One')).toBeTruthy();
    expect(screen.queryByText('Section Two')).toBeNull();
  });

  it('stays on the paged section after a field-value save (no rubber-band to section 1)', async () => {
    // Reported bug (bd voice-ux issues): the simplified view paged to the model's
    // section, but as soon as the field value was confirmed it popped back to
    // section 1. Cause: a confirmation-time updateField in the connection saves
    // the connection's OWN state, whose currentSectionId stays pinned at section 1
    // in continuous mode, and dispatches 'schemaFormStateChange'. The listener
    // must NOT adopt that pinned section over the section the UI has paged to.
    const schema = makeTwoSectionSchema();
    seedContinuousState(schema);

    render(<SchemaForm schema={schema} kitId="test" />);
    await act(async () => {});

    // Voice model focus moves to f2 (section 2); the view pages there.
    await act(async () => {
      capturedOnNextField!('f2');
    });
    expect(screen.getByText('Section Two')).toBeTruthy();
    expect(screen.queryByText('Section One')).toBeNull();

    // Simulate the confirmation: the connection updates f2's value on ITS state,
    // whose currentSectionId is still the pinned first section (sec1). save()
    // dispatches 'schemaFormStateChange', which the listener handles.
    await act(async () => {
      const connState = SchemaFormStateManager.load()!;
      const pinned = { ...connState, currentSectionId: 'sec1' };
      SchemaFormStateManager.updateField(pinned, 'f2', 'Jane', {
        confirmed: true,
        confirmationMethod: 'ai_voice',
      });
    });

    // Still on section 2 -- the value save did NOT rubber-band the view back.
    expect(screen.getByText('Section Two')).toBeTruthy();
    expect(screen.queryByText('Section One')).toBeNull();
  });

  it('does not submit on Enter in continuous mode (Submit button hidden -> onSubmit is a no-op)', async () => {
    // The "Submit Form" button is hidden in continuous mode (no submission
    // target), but the <form onSubmit> is still reachable via Enter in a text
    // input. handleSubmit must no-op in continuous mode so Enter cannot fire the
    // removed button's submit path (bd polyglot-pdf-rvac).
    const schema = makeTwoSectionSchema();
    seedContinuousState(schema);
    const onSubmit = vi.fn();

    const { container } = render(
      <SchemaForm schema={schema} kitId="test" onSubmit={onSubmit} />,
    );
    await act(async () => {});

    const form = container.querySelector('form.schema-form') as HTMLFormElement;
    expect(form).toBeTruthy();
    await act(async () => {
      fireEvent.submit(form);
    });

    // Continuous mode: submit is disabled, so the onSubmit prop is never called.
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does NOT page when continuous mode is off (deprecated section-reset flow owns nav)', async () => {
    // Without continuous mode, section advancement is the manual/section-reset
    // path's job; onNextField must not hijack it by paging the view.
    const schema = makeTwoSectionSchema();
    // Seed a NON-continuous state so init() reuses it (default continuous=false).
    SchemaFormStateManager.init(schema);

    render(<SchemaForm schema={schema} kitId="test" />);
    await act(async () => {});

    expect(screen.getByText('Section One')).toBeTruthy();

    await act(async () => {
      capturedOnNextField!('f2');
    });

    // Still on section 1 -- no auto-paging outside continuous mode.
    expect(screen.getByText('Section One')).toBeTruthy();
    expect(screen.queryByText('Section Two')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Manual edits must not auto-confirm a BLANK value (bd polyglot-pdf-5ovod).
//
// handleFieldChange fires on every keystroke and stamped confirmed:true
// unconditionally, so typing spaces into the React form -- the app's actual
// entry point -- produced a CONFIRMED whitespace entry. That is the exact
// confirmed-but-blank state the rest of the bead had to build a navigation
// recovery arm to rescue, manufactured by the primary UI.
//
// Drives the REAL input the user types into, not the handler directly, so the
// test cannot pass by calling something production does not call.
// ---------------------------------------------------------------------------
describe('manual edit does not confirm a blank value (bd polyglot-pdf-5ovod)', () => {
  function storedEntry(fieldId: string): any {
    const raw = sessionStorage.getItem('schema_form_state');
    if (!raw) return undefined;
    return JSON.parse(raw).fieldValues?.[fieldId];
  }

  it('typing only spaces leaves the field UNCONFIRMED', () => {
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    const input = screen.getByLabelText(/Field One/i) as HTMLInputElement;

    fireEvent.change(input, { target: { value: '   ' } });

    const entry = storedEntry('f1');
    expect(entry?.confirmed, 'whitespace must not auto-confirm').not.toBe(true);
  });

  it('typing a real value STORES it but does NOT verify it (bd polyglot-pdf-uum5g)', () => {
    // This test asserted the OPPOSITE until uum5g: typing auto-confirmed, so
    // every keystroke wrote an audit record. The value half of the old
    // assertion still stands and is kept -- withholding the verification must
    // not cost the user their typing.
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    const input = screen.getByLabelText(/Field One/i) as HTMLInputElement;

    fireEvent.change(input, { target: { value: 'Maria' } });

    const entry = storedEntry('f1');
    expect(entry?.value, 'the typed value must still be stored').toBe('Maria');
    expect(entry?.confirmed, 'typing is not an assertion').not.toBe(true);
    expect(
      entry?.confirmationMethod,
      'no audit record for a keystroke'
    ).toBeUndefined();
  });

  it('clearing a field back to empty leaves it unverified', () => {
    // Deleting your answer is not verifying a blank one. (Unchanged by uum5g --
    // it was already unconfirmed here; kept so the blank path stays pinned now
    // that the non-blank path no longer confirms either.)
    render(<SchemaForm schema={makeSchema()} kitId="test" />);
    const input = screen.getByLabelText(/Field One/i) as HTMLInputElement;

    fireEvent.change(input, { target: { value: 'Maria' } });
    fireEvent.change(input, { target: { value: '' } });

    expect(storedEntry('f1')?.confirmed).not.toBe(true);
  });
});
