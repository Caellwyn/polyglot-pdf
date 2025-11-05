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

export interface SchemaFormProps {
  schema: FormSchema;
  pdfUrl?: string; // URL to original PDF for filling (optional)
  onSubmit?: (fieldValues: Record<string, any>) => void;
  onSectionChange?: (sectionId: string) => void;
}

export function SchemaForm({ schema, pdfUrl, onSubmit, onSectionChange }: SchemaFormProps) {
  const [state, setState] = useState<SchemaFormState>(() => {
    console.log('[SchemaForm] Initial state setup');
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
    console.log(`[SchemaForm] handleFieldChange called: ${fieldId} = ${JSON.stringify(value)}`);

    // Use functional update to avoid stale closure issues
    setState(prevState => {
      console.log(`[SchemaForm] setState functional update - prevState.fieldValues:`, prevState.fieldValues);
      let newState = SchemaFormStateManager.updateField(prevState, fieldId, value);

      // Handle copy_to logic: auto-copy value to target fields
      const field = prevState.schema.fields.find(f => f.id === fieldId);
      if (field?.copy_to && field.copy_to.length > 0) {
        console.log(`[SchemaForm] Field ${fieldId} has copy_to:`, field.copy_to);
        // Copy value to all target fields
        field.copy_to.forEach(targetFieldId => {
          console.log(`[SchemaForm] Copying value from ${fieldId} to ${targetFieldId}`);
          newState = SchemaFormStateManager.updateField(newState, targetFieldId, value);
        });
      }

      console.log(`[SchemaForm] setState functional update - newState.fieldValues:`, newState.fieldValues);
      return newState;
    });

    console.log(`[SchemaForm] setState called with functional update - waiting for React to re-render...`);
  };

  const handleFieldBlur = (fieldId: string) => {
    console.log(`[SchemaForm] handleFieldBlur called for: ${fieldId}`);

    // Validate field on blur
    setState(prevState => {
      const field = prevState.schema.fields.find((f) => f.id === fieldId);
      if (!field) return prevState;

      const value = prevState.fieldValues[fieldId];
      console.log(`[SchemaForm] handleFieldBlur - validating ${fieldId}, value:`, value);
      const error = validateField(field, value);

      const newState = SchemaFormStateManager.setValidationError(prevState, fieldId, error);
      console.log(`[SchemaForm] handleFieldBlur - newState.fieldValues:`, newState.fieldValues);
      return newState;
    });
  };

  const handleNextSection = () => {
    console.log('[handleNextSection] Called, isNavigating:', isNavigating);
    if (isNavigating) {
      console.log('[handleNextSection] Already navigating - ignoring');
      return;
    }

    const nextSection = SchemaFormStateManager.getNextSection(state);
    console.log('[handleNextSection] nextSection:', nextSection?.id);
    if (!nextSection) return;

    // Validate current section before moving
    const currentSection = SchemaFormStateManager.getCurrentSection(state);
    console.log('[handleNextSection] currentSection:', currentSection?.id);

    const isValid = SchemaFormStateManager.isSectionValid(state, currentSection!.id);
    console.log('[handleNextSection] isSectionValid:', isValid);

    if (currentSection && !isValid) {
      console.log('[handleNextSection] Section invalid - showing alert');
      alert("Please complete all required fields before continuing.");
      return;
    }

    console.log('[handleNextSection] Section valid - navigating');

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
    console.log('[handleNextSection] Navigation complete');

    // Clear navigation flag after a short delay
    setTimeout(() => {
      console.log('[handleNextSection] Clearing navigation flag');
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
    console.log('[SchemaForm] Starting PDF download...');

    try {
      const filledPDFBytes = await fillPDF(pdfUrl, state.fieldValues, state.schema);

      // Generate filename from form metadata
      const formNumber = state.schema.form_metadata.form_number || 'form';
      const timestamp = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
      const filename = `${formNumber}-filled-${timestamp}.pdf`;

      downloadPDF(filledPDFBytes, filename);
      console.log('[SchemaForm] PDF downloaded successfully:', filename);
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

  // Debug: Log current state's fieldValues at TOP of render
  console.log(`[SchemaForm] ===== RENDER START =====`);
  console.log(`[SchemaForm] RENDER - state.fieldValues:`, Object.keys(state.fieldValues).length, 'fields with values');
  console.log(`[SchemaForm] RENDER - actual state.fieldValues:`, state.fieldValues);
  console.log(`[SchemaForm] RENDER - state.currentPartId:`, state.currentPartId);

  // Debug section navigation
  console.log(`[SchemaForm] Current section: ${currentSection?.id} (${currentSectionIndex + 1}/${sortedSections.length})`);
  console.log(`[SchemaForm] Next section:`, nextSection?.id || "NONE (last section)");
  console.log(`[SchemaForm] Prev section:`, prevSection?.id || "NONE (first section)");

  return (
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

        {(() => {
          console.log(`[SchemaForm] Rendering navigation button. nextSection = ${nextSection ? nextSection.id : 'NULL'}`);
          return nextSection ? (
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
          );
        })()}
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
  );
}
