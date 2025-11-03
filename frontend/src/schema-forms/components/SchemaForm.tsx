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

export interface SchemaFormProps {
  schema: FormSchema;
  onSubmit?: (fieldValues: Record<string, any>) => void;
  onSectionChange?: (sectionId: string) => void;
}

export function SchemaForm({ schema, onSubmit, onSectionChange }: SchemaFormProps) {
  const [state, setState] = useState<SchemaFormState>(() =>
    SchemaFormStateManager.init(schema)
  );

  // Update state when schema changes
  useEffect(() => {
    const newState = SchemaFormStateManager.init(schema);
    setState(newState);
  }, [schema]);

  // Notify parent of section changes
  useEffect(() => {
    if (onSectionChange) {
      onSectionChange(state.currentSectionId);
    }
  }, [state.currentSectionId, onSectionChange]);

  const handleFieldChange = (fieldId: string, value: any) => {
    const newState = SchemaFormStateManager.updateField(state, fieldId, value);
    setState(newState);
  };

  const handleFieldBlur = (fieldId: string) => {
    // Validate field on blur
    const field = state.schema.fields.find((f) => f.id === fieldId);
    if (!field) return;

    const value = state.fieldValues[fieldId];
    const error = validateField(field, value);

    const newState = SchemaFormStateManager.setValidationError(state, fieldId, error);
    setState(newState);
  };

  const handleNextSection = () => {
    const nextSection = SchemaFormStateManager.getNextSection(state);
    if (!nextSection) return;

    // Validate current section before moving
    const currentSection = SchemaFormStateManager.getCurrentSection(state);
    if (currentSection && !SchemaFormStateManager.isSectionValid(state, currentSection.id)) {
      alert("Please complete all required fields before continuing.");
      return;
    }

    // Mark current section as complete
    let newState = state;
    if (currentSection) {
      newState = SchemaFormStateManager.markSectionComplete(state, currentSection.id);
    }

    // Navigate to next section
    newState = SchemaFormStateManager.navigateToSection(newState, nextSection.id);
    setState(newState);
  };

  const handlePreviousSection = () => {
    const prevSection = SchemaFormStateManager.getPreviousSection(state);
    if (!prevSection) return;

    const newState = SchemaFormStateManager.navigateToSection(state, prevSection.id);
    setState(newState);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

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

  const currentSection = SchemaFormStateManager.getCurrentSection(state);
  const currentFields = SchemaFormStateManager.getCurrentSectionFields(state);
  const nextSection = SchemaFormStateManager.getNextSection(state);
  const prevSection = SchemaFormStateManager.getPreviousSection(state);
  const progress = SchemaFormStateManager.getProgress(state);

  // Sort sections by order for progress display
  const sortedSections = [...state.schema.sections].sort((a, b) => a.order - b.order);
  const currentSectionIndex = sortedSections.findIndex((s) => s.id === state.currentSectionId);

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
  );
}
