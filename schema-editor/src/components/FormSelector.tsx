import React from 'react';
import { AVAILABLE_FORMS, type FormConfig } from '../utils/schemaLoader';

interface FormSelectorProps {
  selectedForm: FormConfig | null;
  onSelectForm: (form: FormConfig) => void;
}

export const FormSelector: React.FC<FormSelectorProps> = ({
  selectedForm,
  onSelectForm,
}) => {
  return (
    <div className="flex items-center gap-4 p-4 bg-white border-b border-gray-200">
      <label className="text-sm font-medium text-gray-700">
        Select Form:
      </label>
      <select
        className="flex-1 max-w-md input"
        value={selectedForm?.schemaPath || ''}
        onChange={(e) => {
          const form = AVAILABLE_FORMS.find(f => f.schemaPath === e.target.value);
          if (form) {
            onSelectForm(form);
          }
        }}
      >
        <option value="">-- Choose a form --</option>
        {AVAILABLE_FORMS.map((form) => (
          <option key={form.schemaPath} value={form.schemaPath}>
            {form.name}
          </option>
        ))}
      </select>
      {selectedForm && (
        <div className="text-sm text-gray-500">
          ({selectedForm.pdfPath.split('/').pop()})
        </div>
      )}
    </div>
  );
};
