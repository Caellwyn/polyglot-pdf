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

import React, { useState, useEffect } from "react";
import type { FormSchema, FormSection } from "../types/schema";
import {
  SchemaFormStateManager,
  type SchemaFormState,
} from "../state/schemaFormState";
import { SectionRenderer } from "./SectionRenderer";
import { validateField } from "../utils/validation";
import { fillPDF, downloadPDF } from "../utils/pdfFiller";
import { VoiceOverlay } from "../../demo/VoiceOverlay";

export interface SchemaFormProps {
  schema: FormSchema;
  pdfUrl?: string; // URL to original PDF for filling (optional)
  onSubmit?: (fieldValues: Record<string, any>) => void;
  onSectionChange?: (sectionId: string) => void;
}

export function SchemaForm({ schema, pdfUrl, onSubmit, onSectionChange }: SchemaFormProps) {
  const [state, setState] = useState<SchemaFormState>(() => {
    return SchemaFormStateManager.init(schema);
  });

  // Prevent rapid navigation/submission (debounce)
  const [isNavigating, setIsNavigating] = useState(false);

  // PDF download state
  const [isDownloadingPDF, setIsDownloadingPDF] = useState(false);

  // NOTE: Removed useEffect that was wiping state on schema changes
  // Schema should not change during form filling, and if it does,
  // we don't want to lose user's data

  // Notify parent of section changes
  useEffect(() => {
    if (onSectionChange) {
      onSectionChange(state.currentPartId); // Can be part ID or section ID
    }
  }, [state.currentPartId, onSectionChange]);

  const handleFieldChange = (fieldId: string, value: any) => {
    // Use functional update to avoid stale closure issues
    setState(prevState => {
      let newState = SchemaFormStateManager.updateField(prevState, fieldId, value);

      // Handle copy_to logic: auto-copy value to target fields
      const field = prevState.schema.fields.find(f => f.id === fieldId);
      if (field?.copy_to && field.copy_to.length > 0) {
        // Copy value to all target fields
        field.copy_to.forEach(targetFieldId => {
          newState = SchemaFormStateManager.updateField(newState, targetFieldId, value);
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

    const nextSection = SchemaFormStateManager.getNextSection(state);
    if (!nextSection) return;

    // Validate current section before moving
    const currentSection = SchemaFormStateManager.getCurrentSection(state);

    const isValid = SchemaFormStateManager.isSectionValid(state, currentSection!.id);

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
      const filledPDFBytes = await fillPDF(pdfUrl, state.fieldValues, state.schema);

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

  const currentSection = SchemaFormStateManager.getCurrentSection(state);
  const currentFields = SchemaFormStateManager.getCurrentSectionFields(state);
  const nextSection = SchemaFormStateManager.getNextSection(state);
  const prevSection = SchemaFormStateManager.getPreviousSection(state);
  const progress = SchemaFormStateManager.getProgress(state);

  // Sort sections by order for progress display
  const sortedSections = [...state.schema.sections].sort((a, b) => a.order - b.order);
  const currentSectionIndex = sortedSections.findIndex((s) => s.id === state.currentPartId);

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

      {/* PDF Download Section */}
      {pdfUrl && (
        <div className="schema-form__pdf-download">
          <button
            type="button"
            onClick={handleDownloadPDF}
            disabled={isDownloadingPDF}
            className="schema-form__download-button"
          >
            {isDownloadingPDF ? '⏳ Generating PDF...' : '📄 Download Filled PDF'}
          </button>
          <p className="schema-form__download-help">
            Download a PDF with all your current answers filled in. You can continue editing the form after downloading.
          </p>
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

    {/* Voice Overlay - Outside form to prevent submit triggers */}
    <VoiceOverlay schema={state.schema} />
    </>
  );
}
