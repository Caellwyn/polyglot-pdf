/**
 * SchemaForm - Main form component that renders schema-driven forms
 *
 * Features:
 * - Section-based rendering
 * - SessionStorage persistence
 * - Validation
 * - Responsive design
 * - Progress tracking
 */
import { resolveSessionToken } from "../../shared/sessionCredential";
import { useAuth } from "../../contexts/AuthContext";

import React, { useState, useEffect, useRef, useCallback } from "react";
import type { FormSchema, FormSection } from "../types/schema";
import {
  SchemaFormStateManager,
  type SchemaFormState,
} from "../state/schemaFormState";
import { SectionRenderer } from "./SectionRenderer";
import { PdfViewErrorBoundary } from "./PdfViewErrorBoundary";
import { PdfPreviewFallback } from "./PdfPreviewFallback";
import { validateField } from "../utils/validation";
import { fillPDF, downloadPDF, printPDF } from "../utils/pdfFiller";
import { unwrapFieldValue } from "../utils/fieldValue";
import { isBlankFieldValue } from "../utils/fieldValue";
import { VerifyFieldModal } from "./VerifyFieldModal";
import { FIELD_HIGHLIGHT_DURATION_MS } from "../utils/fieldHighlight";
import { VoiceOverlay } from "../../demo/VoiceOverlay";
import { VoiceOverlayMobile } from "../../demo/VoiceOverlayMobile";
import { createConnectionManager, type ConnectionManager } from "../../shared/connection";
import { MIC_AUDIO_CONSTRAINTS } from "../../shared/audioConstraints";
import { isTestHarnessEnabled } from "../../shared/config";
import { getStoredViewMode, storeViewMode, initialViewMode, viewModeAfterResize, type ViewMode } from "../../pdf-view/viewMode";

// Lazy chunk boundary: pdfjs-dist and everything else in pdf-view/ load only
// when these components actually render -- i.e. once the user opens the
// Preview view mode or the filled-PDF modal. A session that stays in
// Simplified (the landing view) fetches none of it.
const FilledPreviewModal = React.lazy(() => import("../../pdf-view/FilledPreviewModal"));
const PreviewPane = React.lazy(() => import("../../pdf-view/PreviewPane"));

export interface SchemaFormProps {
  schema: FormSchema;
  kitId: string;
  pdfUrl?: string; // URL to original PDF for filling (optional)
  /** The kit's REAL pdf filename from the manifest (bd polyglot-pdf-vccy).
   * For a PRIVATE kit, pdfUrl is the backend route .../pdf -- deriving the
   * filename from that URL yields the literal "pdf" and 404s the fill. */
  pdfFile?: string;
  onSubmit?: (fieldValues: Record<string, any>) => void;
  onSectionChange?: (sectionId: string) => void;
  /** Pre-selected language from onboarding (skips language selection modal in VoiceOverlay) */
  initialLanguage?: string;
}

export function SchemaForm({ schema, kitId, pdfUrl, pdfFile, onSubmit, onSectionChange, initialLanguage }: SchemaFormProps) {
  const { user } = useAuth();
  // Fresh-token accessor for Sol's intro clip, which is fetched BEFORE any
  // WebSocket exists and so cannot borrow the connection's token plumbing
  // (bd polyglot-pdf-s1iex.5). Same shape as the one handed to
  // createConnectionManager below.
  const getIntroToken = useCallback(
    async () => (await resolveSessionToken(user)),
    [user],
  );
  const [state, setState] = useState<SchemaFormState>(() => {
    return SchemaFormStateManager.init(schema);
  });

  // Mirror the latest state into a ref so callbacks captured once (e.g.
  // handleNextField, held by the ConnectionManager created in a [streamReady]
  // effect) can read CURRENT continuousSessionEnabled / currentSectionId without
  // a stale closure. Same pattern as isMobileRef / connectionManagerRef below.
  const stateRef = useRef<SchemaFormState>(state);
  stateRef.current = state;

  // Prevent rapid navigation/submission (debounce)
  const [isNavigating, setIsNavigating] = useState(false);

  // PDF download/print state
  const [isDownloadingPDF, setIsDownloadingPDF] = useState(false);
  const [isPrintingPDF, setIsPrintingPDF] = useState(false);

  const [showPDFPreview, setShowPDFPreview] = useState(false);

  // Dual view modes (bd vxwj): 'simplified' (the classic linear form) vs
  // 'preview' (the PDF surface). Fresh mounts default Simplified; a stored
  // per-session 'preview' choice is honored at desktop width (mobile always
  // STARTS Simplified, epic rubric #5). Purely presentational -- never in the
  // handshake.
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    const mode = initialViewMode(getStoredViewMode(), window.innerWidth);
    // A mobile-width mount DEMOTES a stored 'preview' choice (epic rubric #5).
    // Persist that demotion, exactly as the resize path does below: otherwise
    // state says Simplified while storage still says preview, and the stale
    // value silently resurrects Preview the next time the same session is
    // opened at desktop width.
    //
    // The guard also fires when NOTHING is stored, writing 'simplified' on a
    // fresh mount. That is deliberate and inert: nothing distinguishes "never
    // chose" from "chose Simplified" (getStoredViewMode's only readers are this
    // line and initialViewMode's `stored ?? 'simplified'`), and it also
    // normalizes a junk stored value.
    if (mode !== getStoredViewMode()) storeViewMode(mode);
    return mode;
  });
  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    storeViewMode(mode);
  };

  // The field the voice model is currently on (from next_field_hint);
  // Preview mode's overlays color it, the P1.3 camera snaps to it.
  const [currentFieldId, setCurrentFieldId] = useState<string | null>(null);

  // Once the current field is CONFIRMED it is done -- clear the marker so its
  // overlay shows green, not a stale orange (the next hint re-sets it). Also
  // covers the last-field / disconnect-after-confirm edge.
  useEffect(() => {
    if (!currentFieldId) return;
    const wrapped = state.fieldValues[currentFieldId];
    if (wrapped && typeof wrapped === 'object' && (wrapped as any).confirmed) {
      setCurrentFieldId(null);
    }
  }, [currentFieldId, state.fieldValues]);

  // Mobile detection. The ref mirrors the state so the mount-once resize effect
  // can read the CURRENT classification (dead-zone hysteresis needs the prior
  // value) without a stale closure, and drive the view-mode reset off the SAME
  // decision (bd polyglot-pdf-ipin).
  const [isMobile, setIsMobile] = useState(false);
  const isMobileRef = useRef(false);

  // Voice overlay state
  // The field awaiting explicit verification (bd polyglot-pdf-96um6). null = no
  // modal. Holds only the id; the value and name are read from live state when
  // rendering, so a background AI fill cannot leave the modal showing a stale
  // value the user would then "verify".
  const [verifyingFieldId, setVerifyingFieldId] = useState<string | null>(null);
  const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(null);
  const connectionManagerRef = useRef<ConnectionManager | null>(null);
  const [status, setStatus] = useState<string>('Ready');
  // Thinking indicator (bd polyglot-pdf-wpw.5): SchemaForm owns the ConnectionManager
  // (it is the shared manager the overlays use), so it must wire onThinkingChange and
  // pass `thinking` down -- the overlays skip their own manager when a shared one
  // exists, so wiring it only in the overlays (as first done) made it a no-op here
  // (fresh-eyes finding).
  const [thinking, setThinking] = useState<boolean>(false);
  const [sharedStream, setSharedStream] = useState<MediaStream | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamReady, setStreamReady] = useState(false);

  // Detect mobile on mount and on resize.
  //
  // HYSTERESIS + DEBOUNCE (bd polyglot-pdf-6vo): switching the overlay remounts it,
  // which re-runs the overlay's mount-time connect and restarts the Gemini session.
  // A single 768px threshold thrashes when window.innerWidth oscillates near it --
  // and the desktop vs mobile overlays have different footprints, so mounting one
  // can change innerWidth and bounce it back (a layout feedback loop observed live:
  // innerWidth flipping 647<->1202 with no real window resize, restarting Gemini
  // every ~second and repeating the disclaimer forever). Two guards break it:
  //   1. A dead-zone band: flip to mobile only below MOBILE_MAX, back to desktop
  //      only above DESKTOP_MIN. Inside the band, keep the current mode (no flip).
  //   2. Debounce: only act on a width that has held steady, so a transient bounce
  //      cannot trigger a remount.
  // The INITIAL classification is exempt from the dead zone (Codex review PR #119):
  // hysteresis is only meaningful once there is a prior state to preserve. On first
  // load it would otherwise leave a dead-zone width (e.g. 720px, which historically
  // rendered mobile) on desktop. So the first evaluate() uses the plain BREAKPOINT;
  // subsequent resizes use the dead zone.
  useEffect(() => {
    const BREAKPOINT = 768;   // classic single threshold, used for INITIAL classify
    const MOBILE_MAX = 700;   // <= this -> mobile (resize)
    const DESKTOP_MIN = 820;  // >= this -> desktop; (700, 820) is the dead zone
    let timer: number | undefined;

    const evaluate = (initial = false) => {
      const w = window.innerWidth;

      // Classify mobile vs desktop with the dead-zone hysteresis, reading the
      // CURRENT value from a ref (the effect runs once, so a captured state
      // value would be stale). This single decision drives BOTH isMobile and
      // the view-mode reset below, so the two can never disagree.
      const prev = isMobileRef.current;
      let nextIsMobile = prev;
      if (initial) {
        nextIsMobile = w <= BREAKPOINT;    // first load: definitive, no dead zone
      } else if (w <= MOBILE_MAX) {
        nextIsMobile = true;
      } else if (w >= DESKTOP_MIN) {
        nextIsMobile = false;
      }
      // else (resize, within dead zone) -> keep `prev` (no flip)

      if (prev !== nextIsMobile) {
        console.log('[SchemaForm] [phone] Mobile mode changed:', nextIsMobile, 'width:', w);
      }
      isMobileRef.current = nextIsMobile;
      setIsMobile(nextIsMobile);

      // A live resize that flips the classification to mobile drops Preview back
      // to Simplified (bd polyglot-pdf-ipin), keeping the
      // mobile-defaults-Simplified intent true mid-session and not only at a
      // fresh mount. Keyed on THIS SAME mobile decision -- not an independent
      // width threshold -- so the view mode can never disagree with which
      // overlay (mobile vs desktop) is showing: a desktop-styled VoiceOverlay
      // never pairs with a mobile-defaulted Simplified form (fresh-eyes finding;
      // the dead zone flips isMobile at <=700, not at 768). One-directional:
      // leaving mobile never auto-restores Preview. Skip the INITIAL classify --
      // the mount already chose the mode via initialViewMode().
      if (!initial && nextIsMobile) {
        setViewMode(prevMode => {
          const nextMode = viewModeAfterResize(prevMode);
          if (nextMode !== prevMode) storeViewMode(nextMode);
          return nextMode;
        });
      }
    };

    const onResize = () => {
      if (timer !== undefined) clearTimeout(timer);
      timer = window.setTimeout(() => evaluate(false), 250);
    };

    evaluate(true); // initial (immediate, no debounce, plain breakpoint)
    window.addEventListener('resize', onResize);
    return () => {
      if (timer !== undefined) clearTimeout(timer);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  // Create shared audio stream EARLY (before overlays render)
  useEffect(() => {
    let mounted = true;

    // TEST harness (bd polyglot-pdf-g8w): skip the eager getUserMedia entirely.
    // The E2E voice harness injects audio via window.__VFF_TEST_INJECT, so it needs
    // no microphone -- and this mount-time request is the FIRST mic touch, BEFORE
    // the connection manager + injection hook exist. In a headless/no-permission
    // browser the prompt can hang (never resolve OR reject), so streamReady would
    // never flip and the manager/hook would never be created -- the no-mic flow
    // would hang before reaching connection.ts's guarded startRecording (Codex
    // review, PR #123). Mark ready immediately with no shared stream.
    if (isTestHarnessEnabled()) {
      console.log('[SchemaForm] TEST harness active -- skipping shared mic stream (audio is injected)');
      setStreamReady(true);
      return () => { mounted = false; };
    }

    async function initSharedStream() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          // Canonical AEC/mic constraints (bd polyglot-pdf-gnmo) plus this
          // site's pinned 16kHz recording rate.
          audio: { ...MIC_AUDIO_CONSTRAINTS, sampleRate: 16000 },
        });

        if (mounted) {
          setSharedStream(stream);
          setStreamReady(true);
        } else {
          stream.getTracks().forEach(track => track.stop());
        }
      } catch (error) {
        console.error('[SchemaForm] Failed to create audio stream:', error);
        if (mounted) {
          setStreamError(error instanceof Error ? error.message : 'Unknown error');
          setStreamReady(true); // Mark as ready even on error so UI can render
        }
      }
    }

    initSharedStream();

    return () => {
      mounted = false;
      if (sharedStream) {
        sharedStream.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  const handleNextField = (fieldId: string | null) => {
    if (!fieldId) return;

    // Preview mode colors the current field's overlay from this (bd ogrt);
    // the P1.3 snap-to camera keys on it too.
    setCurrentFieldId(fieldId);

    // Scroll/highlight the field. If we just advanced the section, the target
    // element does not exist yet (React re-renders on the next tick), so defer
    // the scroll a frame so getElementById can find the newly-mounted element.
    const focusField = () => {
      const element = document.getElementById(fieldId);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        element.classList.add('field-highlight');

        // Remove highlight after the pulse animation completes
        setTimeout(() => {
          element.classList.remove('field-highlight');
        }, FIELD_HIGHLIGHT_DURATION_MS);
      }
    };

    // Continuous mode (bd polyglot-pdf-gz20): the voice model fills across the
    // whole form in one session, but the simplified view still renders ONE
    // section at a time and `currentSectionId` stays pinned to the first section
    // (section advancement is otherwise suppressed). So when the model's focus
    // moves to a field in a different section, that field is not rendered --
    // getElementById returns null and the view is stranded on the first section.
    // Page the UI to the field's section so the simplified view follows the
    // model. setVisibleSection sets ONLY currentSectionId -- it preserves any
    // switch_to_field pin (which navigateToSection would clear) and has no
    // completed-section side effects, unlike the deprecated
    // markSectionComplete/switchToSection nav.
    //
    // Read CURRENT state from stateRef, not the captured `state`: this callback
    // is created once (the ConnectionManager is built in a [streamReady] effect),
    // so the closed-over `state` is frozen at mount (continuous not-yet-enabled,
    // first section).
    const current = stateRef.current;
    if (current.continuousSessionEnabled) {
      const targetSectionId = SchemaFormStateManager.findSectionIdForField(current, fieldId);
      if (targetSectionId && targetSectionId !== current.currentSectionId) {
        setState(prevState =>
          SchemaFormStateManager.setVisibleSection(prevState, targetSectionId)
        );
        // The target element mounts on the next render, so defer the scroll a
        // couple of frames until getElementById can find it.
        requestAnimationFrame(() => requestAnimationFrame(focusField));
        return;
      }
    }

    // Already on the right section (or not continuous / section-less field):
    // the element is present now, scroll immediately.
    focusField();
  };

  // Create connection manager once (only when stream becomes ready)
  useEffect(() => {
    if (connectionManagerRef.current) return;
    if (!streamReady) return; // Wait for stream to be ready

    const initManager = async () => {
      // Pass a fresh-token callback (not a one-shot token) so reconnects --
      // notably the post-disclaimer first-section switch -- re-fetch a valid
      // token instead of connecting tokenless and getting 403 (bd polyglot-pdf-wq0).
      const getToken = async () => (await resolveSessionToken(user));

      const manager = createConnectionManager(
        schema, // Use prop schema, not state.schema
        (newStatus: string) => setStatus(newStatus),
        'English',
        sharedStream || undefined,
        handleNextField,
        getToken,
        (isThinking: boolean) => setThinking(isThinking) // bd polyglot-pdf-wpw.5
      );
      connectionManagerRef.current = manager;
      setConnectionManager(manager);
    };

    initManager();

    return () => {
      if (connectionManagerRef.current) {
        connectionManagerRef.current.disconnect();
        connectionManagerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamReady]); // Only create when stream is ready, ignore schema/sharedStream changes

  // Build simple section index for voice overlay (just section ID -> order mapping)
  const sectionIndex: Record<string, number> = {};
  state.schema.sections.forEach((section) => {
    sectionIndex[section.id] = section.order;
  });
  // Notify parent of section changes
  useEffect(() => {
    if (onSectionChange) {
      onSectionChange(state.currentSectionId);
    }
  }, [state.currentSectionId, onSectionChange]);

  // Set up section change callback for Gemini-triggered section switches
  useEffect(() => {
    window.vffOnSectionChanged = () => {
      console.log('[SchemaForm] Section change triggered by Gemini');
      const newState = SchemaFormStateManager.load();
      if (newState) {
        setState(prevState => {
          // Same continuous-mode guard as the storage listener below: the visible
          // section is UI-only in continuous mode (paged by handleNextField), so
          // never let a persisted section-1-pinned state clobber it (bd voice-ux).
          if (prevState.continuousSessionEnabled) {
            return { ...newState, currentSectionId: prevState.currentSectionId };
          }
          return newState;
        });
      }
    };

    return () => {
      window.vffOnSectionChanged = undefined;
    };
  }, []);

  // Listen for state changes from VoiceOverlay (which updates sessionStorage)
  useEffect(() => {
    const handleStorageChange = () => {
      const newState = SchemaFormStateManager.load();
      if (!newState) return;

      // Update if section changed OR if field values changed (for Gemini updates)
      const sectionChanged = newState.currentSectionId !== state.currentSectionId;
      const fieldsChanged = newState.lastUpdated !== state.lastUpdated;

      if (sectionChanged || fieldsChanged) {
        setState(prevState => {
          // In continuous mode the visible section is UI-only: the voice session
          // fills across the whole form and the persisted/connection state keeps
          // currentSectionId pinned at the first section. A field-value save (e.g.
          // a confirmation) dispatches this event with that pinned section, so
          // blindly adopting newState.currentSectionId rubber-bands the simplified
          // view back to section 1 after every confirmation. Preserve the section
          // the UI has paged to (set by handleNextField/setVisibleSection) and take
          // only the fresh field values (bd voice-ux issues).
          if (prevState.continuousSessionEnabled) {
            return { ...newState, currentSectionId: prevState.currentSectionId };
          }
          return newState;
        });
      }
    };

    // Listen to custom storage events (fired by SchemaFormStateManager.save())
    window.addEventListener('storage', handleStorageChange);

    // Also listen to a custom event for same-window updates
    window.addEventListener('schemaFormStateChange', handleStorageChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('schemaFormStateChange', handleStorageChange);
    };
  }, [state.currentSectionId, state.lastUpdated]);

  const handleFieldChange = (fieldId: string, value: any) => {
    // Use functional update to avoid stale closure issues
    setState(prevState => {
      // Typing does NOT verify (bd polyglot-pdf-uum5g). This fires on EVERY
      // KEYSTROKE, so it was writing a full audit record -- confirmed:true with
      // confirmationMethod:'manual_edit' -- while the user was still mid-word.
      // Measured before the fix: typing "Maria" with no blur and no Tab already
      // stored {"value":"Maria","confirmed":true,
      // "confirmationMethod":"manual_edit"}. "Verified" is load-bearing in this
      // product's audit record (docs/standards/confirmation-and-audit.md); a
      // keystroke is not an assertion.
      //
      // This is the surface the bead's premise MISSED: blur here only validates
      // (handleFieldBlur -> setValidationError), so a fix aimed at "blur" alone
      // would have left the schema form AND the PDF-view popover -- which both
      // route through this handler -- still auto-verifying.
      //
      // The VALUE is still stored; only the verification is withheld, so the
      // field stays in the next-field search (bd polyglot-pdf-a08po re-offers
      // it) until an explicit act verifies it.
      let newState = SchemaFormStateManager.updateField(prevState, fieldId, value, {
        confirmed: false
      });

      // Handle copy_to logic: auto-copy value to target fields
      const field = prevState.schema.fields.find(f => f.id === fieldId);
      if (field?.copy_to && field.copy_to.length > 0) {
        // NOTE this loop is REDUNDANT with the fan-out inside updateField's own
        // write chokepoint (schemaFormState.ts), which already copies to every
        // target on EVERY path. Measured: the chokepoint stamps the target
        // confirmed:true regardless of what is passed here, so this loop cannot
        // change the target's verification either way.
        //
        // And that stamp is CORRECT, deliberately: a copy target is read_only,
        // so the model can neither fill nor skip it -- an UNVERIFIED target is a
        // trap that strands computeNextField on a field nobody can act on. The
        // human did answer the value, on the source; the target inherits that.
        // Left in place because it also keeps the target's VALUE in sync within
        // this reducer's local newState (bd polyglot-pdf-uum5g).
        field.copy_to.forEach(targetFieldId => {
          newState = SchemaFormStateManager.updateField(newState, targetFieldId, value, {
            confirmed: false
          });
        });
      }

      // Resume the next-field search from the field the user just edited
      // (bd polyglot-pdf-a08po) -- see the matching move in connection.ts
      // onManualEdit. Typing is an unambiguous act, so it moves the origin
      // whether or not the model is currently speaking.
      newState = SchemaFormStateManager.setSearchOrigin(newState, fieldId);

      return newState;
    });
  };

  /**
   * The user put the cursor in a field (bd polyglot-pdf-a08po). Move the
   * next-field search origin so the model's context follows them -- silently:
   * this NEVER makes the model speak, it only changes which field is the
   * referent for whatever happens next.
   *
   * Suppressed WHILE ANY AUDIO IS PLAYING. Under DTI the model holds one
   * field's schema at a time and the backend coercion pointer is singular, so
   * retargeting mid-question would leave the model asking about field A while
   * focus says field B -- and the spoken answer would mis-fill. Clicking is
   * also ambiguous (fidgeting); typing is not, which is why handleFieldChange
   * above moves the origin unconditionally and this does not.
   *
   * isAnyAudioPlaying(), NOT isModelSpeaking() -- the union INCLUDING a
   * synthesized clip (outer review, bd polyglot-pdf-a08po). isModelSpeaking()
   * is `activeAudioSources.length > 0`, model PCM only, and audioManager's own
   * docstring calls it "structurally incapable of counting a clip"; the
   * spell-back player deliberately WAITS for that count to hit zero before it
   * plays. So during the whole spell-back window it reads "not speaking" while
   * the user is hearing "K-O-W-A-L-C-Z-Y-K, is that correct?".
   *
   * That window is the dangerous one: name_spellback carries NO field_id on the
   * wire (backend/config.py -- the client resolves the current field itself, so
   * the spelled value can only be a STORED value, never the model's memory), and
   * it resolves via computeNextField. A click that moved the origin mid-clip
   * would make the client spell a DIFFERENT field's value back, and the user --
   * hearing a plausible read-back -- would confirm it. Clip playback is
   * playback, so it suppresses like any other.
   */
  const handleFieldFocus = (fieldId: string) => {
    // Feature-detect every hop: this runs on a raw DOM focus/click, which can
    // fire before the connection manager is built, after teardown, or against a
    // partial manager (the preview-edit tests supply one). A throw here would
    // escape into the field's event handler and break plain typing, so the
    // suppression check must never assume the chain exists -- absent audio
    // means nothing is speaking, so the origin moves.
    const manager = connectionManagerRef.current;
    const audio = typeof manager?.getAudioManager === 'function'
      ? manager.getAudioManager()
      : null;
    if (typeof audio?.isAnyAudioPlaying === 'function' && audio.isAnyAudioPlaying()) {
      return;
    }
    // includesSelf: the user is POINTING at this field, so it must be the next
    // field offered -- not its neighbour (fresh-eyes, criterion 1).
    setState(prevState =>
      SchemaFormStateManager.setSearchOrigin(prevState, fieldId, { includesSelf: true })
    );
  };

  // 4dxt: force-skip a required-but-unanswered field. The user may defer to a
  // translator or have no answer; the field is marked skipped (empty value,
  // satisfies the section-validity gate, renders "needs follow-up", PDF blank).
  const handleFieldSkip = (fieldId: string) => {
    setState(prevState =>
      SchemaFormStateManager.markFieldSkipped(prevState, fieldId, 'manual_edit')
    );
  };

  const handleFieldBlur = (fieldId: string) => {
    // Validate field on blur
    setState(prevState => {
      const field = prevState.schema.fields.find((f) => f.id === fieldId);
      if (!field) return prevState;

      const value = prevState.fieldValues[fieldId];
      const error = validateField(field, value);

      const newState = SchemaFormStateManager.setValidationError(prevState, fieldId, error);
      return newState;
    });
  };

  const handleNextSection = () => {
    if (isNavigating) {
      return;
    }

    // Continuous-session mode (bd polyglot-pdf-x8rt): no sections to advance.
    // Defense-in-depth -- callers (the Next button, handleSubmit's Enter path) are
    // already gated, but guarding the shared mutation point too means a future
    // caller can't reintroduce the section-desync without tripping this.
    if (state.continuousSessionEnabled) return;

    // Use section-based navigation
    const nextSection = SchemaFormStateManager.getNextSection(state);
    if (!nextSection) return;

    // Validate current section before moving
    const currentSection = SchemaFormStateManager.getCurrentSection(state);

    const isValid = currentSection ? SchemaFormStateManager.isSectionValid(state, currentSection.id) : true;

    if (currentSection && !isValid) {
      alert("Please complete all required fields before continuing.");
      return;
    }

    // Set navigation flag
    setIsNavigating(true);

    // Mark current section as complete
    let newState = state;
    if (currentSection) {
      newState = SchemaFormStateManager.markSectionComplete(state, currentSection.id);
    }

    // Navigate to next section
    newState = SchemaFormStateManager.navigateToSection(newState, nextSection.id);
    setState(newState);

    // Clear navigation flag after a short delay
    setTimeout(() => {
      setIsNavigating(false);
    }, 300);
  };

  const handlePreviousSection = () => {
    // Continuous-session mode (bd polyglot-pdf-x8rt): no sections to navigate.
    // Defense-in-depth, matching handleNextSection (the Previous button is already
    // hidden in continuous mode, so this only guards a stray/future caller).
    if (state.continuousSessionEnabled) return;
    // Use section-based navigation
    const prevSection = SchemaFormStateManager.getPreviousSection(state);
    if (!prevSection) return;

    const newState = SchemaFormStateManager.navigateToSection(state, prevSection.id);
    setState(newState);
  };

  /**
   * Enter on a FILLED field opens the verify modal (bd polyglot-pdf-96um6).
   *
   * This is the keyboard path to an audit claim. Typing stopped producing one in
   * bd polyglot-pdf-uum5g, so without this gesture a typing-only user cannot
   * finish a form at all.
   *
   * Bound at the FORM, not threaded through every field component: Enter bubbles
   * from whichever input has focus, and every field type renders id={field.id}
   * (TextField, TextAreaField, DateField, SelectField, CheckboxField), so one
   * handler covers them all with no prop drilling.
   *
   * SCOPE, deliberately narrow: only a field holding a real value opens the
   * modal. On an empty or whitespace-only field Enter keeps its existing
   * behaviour, because there is nothing to verify -- and because Enter today
   * reaches <form onSubmit> and advances the section, which is a shortcut people
   * may rely on. Where the modal DOES open we preventDefault, so that submit
   * never fires and the section cannot move out from under the dialog.
   */
  const handleFormKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (e.key !== 'Enter') return;
    const target = e.target as HTMLElement | null;
    const fieldId = target?.id;
    if (!fieldId) return;
    // A textarea's Enter is a newline, not a submit -- leave it alone.
    if (target?.tagName === 'TEXTAREA') return;
    const field = state.schema.fields.find(f => f.id === fieldId);
    if (!field) return;

    const value = unwrapFieldValue(state.fieldValues[fieldId]);
    if (isBlankFieldValue(value)) return;

    e.preventDefault();
    e.stopPropagation();
    setVerifyingFieldId(fieldId);
  };

  /**
   * The user asserted the answer is correct. Writes through the SAME path the
   * verbal confirm uses (confirmField), so the audit record has one shape
   * whatever gesture produced it, then tells the model the new STATE through the
   * established manual_field_update protocol -- a verify does not reach the model
   * on its own (measured: the notify fires on a DOM value change, and verifying
   * changes no value).
   */
  const handleVerifyConfirmed = () => {
    const fieldId = verifyingFieldId;
    if (!fieldId) return;
    setState(prevState => {
      // confirmField SAVES internally, so no explicit save here -- a second one
      // double-fires the schemaFormStateChange event (fresh-eyes finding).
      const next = SchemaFormStateManager.confirmField(prevState, fieldId, 'manual_edit');
      const field = next.schema.fields.find(f => f.id === fieldId);
      const conn = connectionManagerRef.current;
      if (conn?.sendManualFieldUpdate) {
        conn.sendManualFieldUpdate(
          fieldId,
          field?.name || fieldId,
          unwrapFieldValue(next.fieldValues[fieldId]),
          true
        );
      }
      return next;
    });
    setVerifyingFieldId(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    console.log('[handleSubmit] Form submit triggered! isNavigating:', isNavigating);
    e.preventDefault();

    // Continuous-session mode (bd polyglot-pdf-rvac): the Submit Form button is
    // hidden (no downstream submission target yet), but the <form onSubmit> is
    // still reachable via Enter in a text input. Make submit a no-op here so the
    // Enter key cannot trigger the validate/alert "final submit" the removed
    // button would have -- same defense-in-depth as handleNextSection/Previous.
    if (state.continuousSessionEnabled) {
      console.log('[handleSubmit] Continuous mode - submit is disabled (no target)');
      return;
    }

    // Ignore if we're currently navigating (prevents double-trigger from click event)
    if (isNavigating) {
      console.log('[handleSubmit] Currently navigating - ignoring submit');
      return;
    }

    // Check if there's a next section - if so, don't submit, just navigate.
    // Continuous-session mode (bd polyglot-pdf-x8rt): the form is one session with
    // no sections to navigate, so SKIP this branch -- otherwise pressing Enter in a
    // field (native form submit) would flip the visible section away from the live
    // continuous voice session (the schema still HAS sections; continuity is a
    // client-side session concern). This is the Enter-key sibling of hiding the
    // Previous/Next buttons above.
    const nextSection = state.continuousSessionEnabled
      ? null
      : SchemaFormStateManager.getNextSection(state);
    if (nextSection) {
      console.log('[handleSubmit] Next section exists - triggering navigation instead of submit');
      handleNextSection();
      return;
    }

    console.log('[handleSubmit] No next section - this is the final submit');

    // Validate all fields
    let hasErrors = false;
    let newState = state;

    for (const field of state.schema.fields) {
      const value = state.fieldValues[field.id];
      const error = validateField(field, value);

      if (error) {
        hasErrors = true;
        newState = SchemaFormStateManager.setValidationError(newState, field.id, error);
      }
    }

    if (hasErrors) {
      setState(newState);
      alert("Please fix all validation errors before submitting.");
      return;
    }

    // Submit form
    if (onSubmit) {
      onSubmit(state.fieldValues);
    }
  };

  // SAVE NUDGE BRIDGE (bd polyglot-pdf-dft1). The nudge lives in the voice
  // overlay, which does not own the fill/download path, so it asks for a save
  // by event rather than reaching across components.
  //
  // Without this listener the nudge's Save button silently does NOTHING while
  // telling the client they saved -- and it permanently silences both nudges,
  // so they never learn otherwise. The ending variant has no dismiss button,
  // making that dead button its only exit. Found in cross-surface review.
  useEffect(() => {
    const onSaveRequested = () => { void handleDownloadPDF(); };
    window.addEventListener('polyglot:save-form', onSaveRequested);
    return () => window.removeEventListener('polyglot:save-form', onSaveRequested);
  });

  const handleDownloadPDF = async () => {
    if (!pdfUrl) {
      alert("PDF URL not configured. Cannot download filled PDF.");
      return;
    }

    setIsDownloadingPDF(true);

    try {
      // Unwrap FieldValue objects to get raw values for PDF filling
      const unwrappedFieldValues: Record<string, any> = {};
      for (const [fieldId, value] of Object.entries(state.fieldValues)) {
        unwrappedFieldValues[fieldId] = unwrapFieldValue(value);
      }

      console.log('[SchemaForm] Unwrapped field values for PDF filling:', {
        original_count: Object.keys(state.fieldValues).length,
        unwrapped_count: Object.keys(unwrappedFieldValues).length,
        sample: Object.entries(unwrappedFieldValues).slice(0, 3),
      });

      const filledPDFBytes = await fillPDF(
        kitId, pdfUrl, unwrappedFieldValues, state.schema,
        async () => (await resolveSessionToken(user)),
        pdfFile,
        state.formSessionId,   // resume stamp (bd polyglot-pdf-dft1)
      );

      // Generate filename from form metadata
      const formNumber = state.schema.form_metadata.form_number || 'form';
      const timestamp = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
      const filename = `${formNumber}-filled-${timestamp}.pdf`;

      downloadPDF(filledPDFBytes, filename);
    } catch (error) {
      console.error('[SchemaForm] PDF download failed:', error);
      alert('Failed to download PDF. Check console for details.');
    } finally {
      setIsDownloadingPDF(false);
    }
  };

  const handlePrintPDF = async () => {
    if (!pdfUrl) {
      alert("PDF URL not configured. Cannot print filled PDF.");
      return;
    }

    setIsPrintingPDF(true);

    try {
      // Unwrap FieldValue objects to get raw values for PDF filling
      const unwrappedFieldValues: Record<string, any> = {};
      for (const [fieldId, value] of Object.entries(state.fieldValues)) {
        unwrappedFieldValues[fieldId] = unwrapFieldValue(value);
      }

      console.log('[SchemaForm] Preparing PDF for printing with unwrapped values');

      const filledPDFBytes = await fillPDF(
        kitId, pdfUrl, unwrappedFieldValues, state.schema,
        async () => (await resolveSessionToken(user)),
        pdfFile,
        state.formSessionId,   // resume stamp (bd polyglot-pdf-dft1)
      );

      // Open print dialog
      printPDF(filledPDFBytes);
    } catch (error) {
      console.error('[SchemaForm] PDF print failed:', error);
      alert('Failed to print PDF. Check console for details.');
    } finally {
      setIsPrintingPDF(false);
    }
  };

  const currentSection = SchemaFormStateManager.getCurrentSection(state);
  const currentFields = SchemaFormStateManager.getCurrentSectionFields(state);
  const nextSection = SchemaFormStateManager.getNextSection(state);
  const prevSection = SchemaFormStateManager.getPreviousSection(state);
  const progress = SchemaFormStateManager.getProgress(state);

  // Sort sections by order for progress display
  const sortedSections = [...state.schema.sections].sort((a, b) => a.order - b.order);
  const currentSectionIndex = currentSection ? sortedSections.findIndex((s) => s.id === currentSection.id) : -1;

  return (
    <>
      {/* View-mode toggle (bd vxwj). The voice overlay + the ConnectionManager
          live OUTSIDE the switched container below, so toggling views never
          remounts them or disturbs the session. */}
      <div className="schema-form__view-toggle" role="tablist" aria-label="Form view">
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'simplified'}
          className={`schema-form__view-toggle-button${viewMode === 'simplified' ? ' schema-form__view-toggle-button--active' : ''}`}
          onClick={() => handleViewModeChange('simplified')}
        >
          Simplified
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'preview'}
          className={`schema-form__view-toggle-button${viewMode === 'preview' ? ' schema-form__view-toggle-button--active' : ''}`}
          onClick={() => handleViewModeChange('preview')}
        >
          Preview
        </button>
      </div>

      {verifyingFieldId && (() => {
        const vField = state.schema.fields.find(f => f.id === verifyingFieldId);
        const vValue = unwrapFieldValue(state.fieldValues[verifyingFieldId]);
        return (
          <VerifyFieldModal
            isOpen
            fieldName={vField?.name || verifyingFieldId}
            value={
              typeof vValue === 'boolean' ? vValue : vValue == null ? '' : String(vValue)
            }
            selectedLanguage={initialLanguage || 'English'}
            onVerify={handleVerifyConfirmed}
            onCancel={() => setVerifyingFieldId(null)}
          />
        );
      })()}

      {/* Enter->verify is bound HERE, around BOTH views (bd polyglot-pdf-96um6).
          It was originally on the <form>, which is the Simplified view ONLY -- so
          the PDF view had no keyboard verify path at all, reproducing the exact
          hole this bead exists to close. Fresh-eyes caught it. */}
      <div onKeyDown={handleFormKeyDown} className="schema-form__view-container">
      {viewMode === 'preview' ? (
        <PdfViewErrorBoundary
          fallback={
            // Inline styles on purpose: pdf-view.css (which defines
            // pdf-preview-pane__notice) is imported only by the lazy pdf-view
            // chunk, so it is unavailable exactly when this fallback renders
            // (the chunk failed to load) -- see PdfPreviewFallback.tsx.
            <div
              className="pdf-preview-pane__notice"
              style={{
                maxWidth: '64rem',
                margin: '1rem auto',
                padding: '1rem',
                background: '#fefce8',
                border: '1px solid #fde68a',
                borderRadius: '6px',
                color: '#713f12',
              }}
            >
              The PDF preview could not be loaded. Check your connection and reload the page to
              try again.
            </div>
          }
        >
          <React.Suspense
            fallback={<div className="pdf-preview-pane__notice">Loading the preview...</div>}
          >
            <PreviewPane
              pdfUrl={pdfUrl}
              schema={state.schema}
              fieldValues={state.fieldValues}
              currentFieldId={currentFieldId}
              validationErrors={state.validationErrors}
              onFieldChange={handleFieldChange}
              onFieldBlur={handleFieldBlur}
              onFieldFocus={handleFieldFocus}
            />
          </React.Suspense>
        </PdfViewErrorBoundary>
      ) : (
      <form className="schema-form" onSubmit={handleSubmit} onKeyDown={handleFormKeyDown}>

        {/* Form Header */}
        <div className="schema-form__header">
          <h1 className="schema-form__title">{state.schema.form_metadata.title}</h1>
          {state.schema.form_metadata.description && (
            <p className="schema-form__description">{state.schema.form_metadata.description}</p>
          )}

          {/* Progress Bar */}
          <div className="schema-form__progress">
            <div className="schema-form__progress-bar">
              <div
                className="schema-form__progress-fill"
                style={{ width: `${progress}%` }}
                role="progressbar"
                aria-valuenow={progress}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
            <p className="schema-form__progress-text">
              Section {currentSectionIndex + 1} of {sortedSections.length} • {Math.round(progress)}%
              complete
            </p>
          </div>
        </div>

        {/* Current Section */}
        {currentSection && (
          <SectionRenderer
            section={currentSection}
            fields={currentFields}
            fieldValues={state.fieldValues}
            validationErrors={state.validationErrors}
            onFieldChange={handleFieldChange}
            onFieldBlur={handleFieldBlur}
            onFieldFocus={handleFieldFocus}
            onFieldSkip={handleFieldSkip}
          />
        )}

        {/* Navigation. In continuous-session mode (bd polyglot-pdf-x8rt) the form
            is one session with no sections to navigate -- hide the Previous/Next
            section buttons so a manual section jump (which desyncs the visible
            section from the live voice session) is unreachable. The Submit Form
            button is hidden for now: there is no downstream system to submit to,
            so it only confused testers (bd voice-ux issues). Re-add it here when a
            real submission target exists. */}
        {!state.continuousSessionEnabled && (
          <div className="schema-form__navigation">
            {prevSection && (
              <button
                type="button"
                onClick={handlePreviousSection}
                className="schema-form__nav-button schema-form__nav-button--prev"
              >
                ← Previous
              </button>
            )}

            {nextSection && (
              <button
                type="button"
                onClick={handleNextSection}
                className="schema-form__nav-button schema-form__nav-button--next"
              >
                Next →
              </button>
            )}
          </div>
        )}

        {/* Legal Warnings */}
        {state.schema.legal_warnings && state.schema.legal_warnings.length > 0 && (
          <div className="schema-form__legal">
            {state.schema.legal_warnings.map((warning, index) => (
              <p key={index} className="schema-form__legal-warning">
                {warning}
              </p>
            ))}
          </div>
        )}
      </form>
      )}

      {/* PDF Download/Print Section - Outside form to avoid submission conflicts */}
      {pdfUrl && (
        <div className="schema-form__pdf-download">
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={handlePrintPDF}
              disabled={isPrintingPDF || isDownloadingPDF}
              className="schema-form__download-button"
              style={{ backgroundColor: '#28a745' }}
            >
              {isPrintingPDF ? '⏳ Preparing to Print...' : '🖨️ Print Filled PDF'}
            </button>
            <button
              type="button"
              onClick={handleDownloadPDF}
              disabled={isDownloadingPDF || isPrintingPDF}
              className="schema-form__download-button"
            >
              {isDownloadingPDF ? '⏳ Generating PDF...' : '📄 Download Filled PDF'}
            </button>
            <button
              type="button"
              onClick={() => setShowPDFPreview(true)}
              disabled={isDownloadingPDF || isPrintingPDF}
              className="schema-form__download-button"
              style={{ backgroundColor: '#6c757d' }}
            >
              Preview Filled PDF
            </button>
          </div>
          <p className="schema-form__download-help">
            Print or download a PDF with all your current answers filled in. You can continue editing the form after printing/downloading.
          </p>
        </div>
      )}

      {/* True filled-PDF preview (epic js7q): the modal fills via the same
          /api/fill-pdf call as download/print and renders the bytes. */}
      {showPDFPreview && pdfUrl && (
        <PdfViewErrorBoundary
          fallback={<PdfPreviewFallback onClose={() => setShowPDFPreview(false)} />}
        >
          <React.Suspense fallback={null}>
            <FilledPreviewModal
              kitId={kitId}
              pdfUrl={pdfUrl}
              pdfFile={pdfFile}
              schema={state.schema}
              fieldValues={state.fieldValues}
              onClose={() => setShowPDFPreview(false)}
            />
          </React.Suspense>
        </PdfViewErrorBoundary>
      )}

      {/* Voice Overlay - Render mobile or desktop based on screen size */}
      {/* Only render when stream is ready to prevent race conditions */}
      {connectionManager && streamReady && (
        isMobile ? (
          <VoiceOverlayMobile
            schema={state.schema}
            connectionManager={connectionManager}
            sharedStream={sharedStream}
            streamError={streamError}
            status={status}
            thinking={thinking}
            initialLanguage={initialLanguage}
            getToken={getIntroToken}
          />
        ) : (
          <VoiceOverlay
            schema={state.schema}
            connectionManager={connectionManager}
            status={status}
            thinking={thinking}
            sharedStream={sharedStream}
            streamError={streamError}
            initialLanguage={initialLanguage}
            getToken={getIntroToken}
          />
        )
      )}
      </div>
    </>
  );
}