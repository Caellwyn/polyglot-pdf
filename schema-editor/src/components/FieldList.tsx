import React from 'react';
import type { FormSchema, FormField, FormSection } from '../types/schema';
import { checkFieldComplete } from '../utils/validation';

interface FieldListProps {
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
}

export const FieldList: React.FC<FieldListProps> = ({
  schema,
  selectedFieldId,
  onSelectField,
}) => {
  const [expandedSections, setExpandedSections] = React.useState<Set<string>>(
    new Set(schema.sections.map(s => s.id))
  );

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
      }
      return next;
    });
  };

  const getFieldStatus = (field: FormField) => {
    const status = checkFieldComplete(field);
    if (status.isComplete) return 'complete';
    if (status.needsReview) return 'review';
    return 'error';
  };

  const getFieldIcon = (status: string) => {
    if (status === 'complete') {
      return (
        <svg className="w-4 h-4 text-green-600" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clipRule="evenodd"
          />
        </svg>
      );
    }
    if (status === 'review') {
      return (
        <svg className="w-4 h-4 text-yellow-600" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
            clipRule="evenodd"
          />
        </svg>
      );
    }
    return (
      <svg className="w-4 h-4 text-red-600" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
          clipRule="evenodd"
        />
      </svg>
    );
  };

  // Build field lookup
  const fieldsById = React.useMemo(() => {
    const map = new Map<string, FormField>();
    for (const field of schema.fields) {
      map.set(field.id, field);
    }
    return map;
  }, [schema.fields]);

  // Group fields by section
  const sectionedFields = React.useMemo(() => {
    const map = new Map<string, FormField[]>();

    for (const section of schema.sections) {
      const fields = section.fields
        .map(id => fieldsById.get(id))
        .filter((f): f is FormField => f !== undefined);
      map.set(section.id, fields);
    }

    // Fields without section
    const orphanFields = schema.fields.filter(f => !f.section_id);
    if (orphanFields.length > 0) {
      map.set('_orphan', orphanFields);
    }

    return map;
  }, [schema.sections, schema.fields, fieldsById]);

  return (
    <div className="h-full overflow-auto custom-scrollbar bg-gray-50">
      <div className="p-2 space-y-1">
        {/* Render sections */}
        {schema.sections.map(section => {
          const fields = sectionedFields.get(section.id) || [];
          const isExpanded = expandedSections.has(section.id);

          return (
            <div key={section.id} className="bg-white rounded-md shadow-sm">
              {/* Section Header */}
              <button
                className="w-full flex items-center gap-2 p-2 text-left hover:bg-gray-50 transition-colors"
                onClick={() => toggleSection(section.id)}
              >
                <svg
                  className={`w-4 h-4 text-gray-500 transition-transform ${
                    isExpanded ? 'transform rotate-90' : ''
                  }`}
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="text-sm font-medium text-gray-700 flex-1">
                  {section.label}
                </span>
                <span className="text-xs text-gray-500">({fields.length})</span>
              </button>

              {/* Fields */}
              {isExpanded && (
                <div className="border-t border-gray-100">
                  {fields.map(field => {
                    const status = getFieldStatus(field);
                    const isSelected = field.id === selectedFieldId;

                    return (
                      <button
                        key={field.id}
                        className={`w-full flex items-center gap-2 p-2 text-left text-sm hover:bg-gray-50 transition-colors ${
                          isSelected ? 'bg-primary-50 border-l-2 border-primary-500' : ''
                        }`}
                        onClick={() => onSelectField(field.id)}
                      >
                        {getFieldIcon(status)}
                        <span className="flex-1 truncate text-gray-700">
                          {field.spoken_name || field.id}
                        </span>
                        <span className="text-xs text-gray-400 font-mono">
                          [{field.type}]
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {/* Orphan fields (no section) */}
        {sectionedFields.has('_orphan') && (
          <div className="bg-white rounded-md shadow-sm">
            <div className="p-2 bg-gray-100 text-sm font-medium text-gray-700">
              Uncategorized Fields
            </div>
            {(sectionedFields.get('_orphan') || []).map(field => {
              const status = getFieldStatus(field);
              const isSelected = field.id === selectedFieldId;

              return (
                <button
                  key={field.id}
                  className={`w-full flex items-center gap-2 p-2 text-left text-sm hover:bg-gray-50 transition-colors ${
                    isSelected ? 'bg-primary-50 border-l-2 border-primary-500' : ''
                  }`}
                  onClick={() => onSelectField(field.id)}
                >
                  {getFieldIcon(status)}
                  <span className="flex-1 truncate text-gray-700">
                    {field.spoken_name || field.id}
                  </span>
                  <span className="text-xs text-gray-400 font-mono">
                    [{field.type}]
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
