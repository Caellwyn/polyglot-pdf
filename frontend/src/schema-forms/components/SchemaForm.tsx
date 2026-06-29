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
import { useAuth } from "../../contexts/AuthContext";

import React, { useState, useEffect, useRef } from "react";
import type { FormSchema, FormSection } from "../types/schema";
import {
  SchemaFormStateManager,
  type SchemaFormState,
} from "../state/schemaFormState";
import { SectionRenderer } from "./SectionRenderer";
import { validateField } from "../utils/validation";
import { fillPDF, downloadPDF, printPDF } from "../utils/pdfFiller";
import { unwrapFieldValue } from "../utils/fieldValue";
import { FIELD_HIGHLIGHT_DURATION_MS } from "../utils/fieldHighlight";
import { VoiceOverlay } from "../../demo/VoiceOverlay";
import { VoiceOverlayMobile } from "../../demo/VoiceOverlayMobile";
import { createConnectionManager, type ConnectionManager } from "../../shared/connection";
import { isTestHarnessEnabled } from "../../shared/config";

export interface SchemaFormProps {
  schema: FormSchema;
  kitId: string;
  pdfUrl?: string; // URL to original PDF for filling (optional)
  onSubmit?: (fieldValues: Record<string, any>) => void;
  onSectionChange?: (sectionId: string) => void;
  /** Pre-selected language from onboarding (skips language selection modal in VoiceOverlay) */
  initialLanguage?: string;
}

export function SchemaForm({ schema, kitId, pdfUrl, onSubmit, onSectionChange, initialLanguage }: SchemaFormProps) {
  const { user } = useAuth();
  const [state, setState] = useState<SchemaFormState>(() => {
    return SchemaFormStateManager.init(schema);
  });

  // Prevent rapid navigation/submission (debounce)
  const [isNavigating, setIsNavigating] = useState(false);

  // PDF download/print state
  const [isDownloadingPDF, setIsDownloadingPDF] = useState(false);
  const [isPrintingPDF, setIsPrintingPDF] = useState(false);

  // Mobile detection
  const [isMobile, setIsMobile] = useState(false);

  // Voice overlay state
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
      setIsMobile(prev => {
        let next = prev;
        if (initial) {
          next = w <= BREAKPOINT;          // first load: definitive, no dead zone
        } else if (w <= MOBILE_MAX) {
          next = true;
        } else if (w >= DESKTOP_MIN) {
          next = false;
        }
        // else (resize, within dead zone) -> keep `prev` (no flip)
        if (prev !== next) {
          console.log('[SchemaForm] [phone] Mobile mode changed:', next, 'width:', w);
        }
        return next;
      });
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
          audio: {
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
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

  // Create connection manager once (only when stream becomes ready)
  useEffect(() => {
    if (connectionManagerRef.current) return;
    if (!streamReady) return; // Wait for stream to be ready

    const initManager = async () => {
      // Pass a fresh-token callback (not a one-shot token) so reconnects --
      // notably the post-disclaimer first-section switch -- re-fetch a valid
      // token instead of connecting tokenless and getting 403 (bd polyglot-pdf-wq0).
      const getToken = async () => (user ? await user.getIdToken() : undefined);

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
        setState(newState);
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
        setState(newState);
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
      // Manual edits from React UI are auto-confirmed (user explicitly typed/selected value)
      let newState = SchemaFormStateManager.updateField(prevState, fieldId, value, {
        confirmed: true,
        confirmationMethod: 'manual_edit'
      });

      // Handle copy_to logic: auto-copy value to target fields
      const field = prevState.schema.fields.find(f => f.id === fieldId);
      if (field?.copy_to && field.copy_to.length > 0) {
        // Copy value to all target fields (also auto-confirmed)
        field.copy_to.forEach(targetFieldId => {
          newState = SchemaFormStateManager.updateField(newState, targetFieldId, value, {
            confirmed: true,
            confirmationMethod: 'manual_edit'
          });
        });
      }

      return newState;
    });
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
    // Use section-based navigation
    const prevSection = SchemaFormStateManager.getPreviousSection(state);
    if (!prevSection) return;

    const newState = SchemaFormStateManager.navigateToSection(state, prevSection.id);
    setState(newState);
  };

  const handleSubmit = (e: React.FormEvent) => {
    console.log('[handleSubmit] Form submit triggered! isNavigating:', isNavigating);
    e.preventDefault();

    // Ignore if we're currently navigating (prevents double-trigger from click event)
    if (isNavigating) {
      console.log('[handleSubmit] Currently navigating - ignoring submit');
      return;
    }

    // Check if there's a next section - if so, don't submit, just navigate
    const nextSection = SchemaFormStateManager.getNextSection(state);
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

      const filledPDFBytes = await fillPDF(kitId, pdfUrl, unwrappedFieldValues, state.schema);

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

      const filledPDFBytes = await fillPDF(kitId, pdfUrl, unwrappedFieldValues, state.schema);

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
      <form className="schema-form" onSubmit={handleSubmit}>
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
          />
        )}

        {/* Navigation */}
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

          {nextSection ? (
            <button
              type="button"
              onClick={handleNextSection}
              className="schema-form__nav-button schema-form__nav-button--next"
            >
              Next →
            </button>
          ) : (
            <button type="submit" className="schema-form__nav-button schema-form__nav-button--submit">
              Submit Form
            </button>
          )}
        </div>

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
          </div>
          <p className="schema-form__download-help">
            Print or download a PDF with all your current answers filled in. You can continue editing the form after printing/downloading.
          </p>
        </div>
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
          />
        )
      )}
    </>
  );
}