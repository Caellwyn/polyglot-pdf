import React from 'react';
import type { FormSchema, FormField } from '../types/schema';
import { checkFieldComplete } from '../utils/validation';

interface FieldListProps {
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
  onReorderFields?: (sectionId: string, fieldIds: string[]) => void;
  onMoveOption?: (sourceFieldId: string, optionIndex: number, targetFieldId: string) => void;
}

export const FieldList: React.FC<FieldListProps> = ({
  schema,
  selectedFieldId,
  onSelectField,
  onReorderFields,
  onMoveOption,
}) => {
  const [expandedSections, setExpandedSections] = React.useState<Set<string>>(
    new Set(schema.sections.map(s => s.id))
  );
  const [expandedFields, setExpandedFields] = React.useState<Set<string>>(new Set());
  const [draggedField, setDraggedField] = React.useState<{ fieldId: string; sectionId: string } | null>(null);
  const [draggedOption, setDraggedOption] = React.useState<{ fieldId: string; optionIndex: number } | null>(null);
  const [dragOverField, setDragOverField] = React.useState<string | null>(null);
  const fieldRefs = React.useRef<Map<string, HTMLButtonElement>>(new Map());

  const handleDragStart = (fieldId: string, sectionId: string) => (e: React.DragEvent) => {
    setDraggedField({ fieldId, sectionId });
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (fieldId: string) => (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverField(fieldId);
  };

  const handleDragLeave = () => {
    setDragOverField(null);
  };

  const handleDrop = (targetFieldId: string, targetSectionId: string) => (e: React.DragEvent) => {
    e.preventDefault();
    setDragOverField(null);

    // Handle option drop (moving option to another field)
    if (draggedOption) {
      handleFieldDropForOption(targetFieldId)(e);
      return;
    }

    // Handle field reorder
    if (!draggedField || !onReorderFields) return;
    if (draggedField.fieldId === targetFieldId) return;
    
    // Only allow reordering within the same section
    if (draggedField.sectionId !== targetSectionId) {
      setDraggedField(null);
      return;
    }

    const section = schema.sections.find(s => s.id === targetSectionId);
    if (!section) return;

    const currentFields = [...section.fields];
    const draggedIndex = currentFields.indexOf(draggedField.fieldId);
    const targetIndex = currentFields.indexOf(targetFieldId);

    if (draggedIndex === -1 || targetIndex === -1) return;

    // Remove dragged field and insert at new position
    currentFields.splice(draggedIndex, 1);
    currentFields.splice(targetIndex, 0, draggedField.fieldId);

    onReorderFields(targetSectionId, currentFields);
    setDraggedField(null);
  };

  const handleDragEnd = () => {
    setDraggedField(null);
    setDraggedOption(null);
    setDragOverField(null);
  };

  // Option drag handlers
  const handleOptionDragStart = (fieldId: string, optionIndex: number) => (e: React.DragEvent) => {
    e.stopPropagation(); // Prevent field drag
    setDraggedOption({ fieldId, optionIndex });
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleFieldDropForOption = (targetFieldId: string) => (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverField(null);

    if (!draggedOption || !onMoveOption) return;
    if (draggedOption.fieldId === targetFieldId) return; // Same field, no move needed

    const targetField = schema.fields.find(f => f.id === targetFieldId);
    
    // Only allow dropping into radio/checkbox fields
    if (!targetField || (targetField.type !== 'radio' && targetField.type !== 'checkbox')) {
      setDraggedOption(null);
      return;
    }

    onMoveOption(draggedOption.fieldId, draggedOption.optionIndex, targetFieldId);
    setDraggedOption(null);
  };

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

  const toggleField = (fieldId: string) => {
    setExpandedFields(prev => {
      const next = new Set(prev);
      if (next.has(fieldId)) {
        next.delete(fieldId);
      } else {
        next.add(fieldId);
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

  // Auto-scroll to selected field when selection changes
  React.useEffect(() => {
    if (!selectedFieldId) return;

    // Find the field element
    const fieldEl = fieldRefs.current.get(selectedFieldId);
    if (!fieldEl) return;

    // Find and expand the section containing this field
    const field = fieldsById.get(selectedFieldId);
    if (field?.section_id) {
      setExpandedSections(prev => {
        const next = new Set(prev);
        next.add(field.section_id!);
        return next;
      });
    }

    // Scroll field into view (with a small delay to allow section expansion)
    setTimeout(() => {
      fieldEl.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }, 100);
  }, [selectedFieldId, fieldsById]);

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
                    const isDragOver = dragOverField === field.id;
                    const isDragging = draggedField?.fieldId === field.id;
                    const hasOptions = field.options && field.options.length > 0;
                    const isFieldExpanded = expandedFields.has(field.id);
                    const canAcceptOption = draggedOption && (field.type === 'radio' || field.type === 'checkbox') && draggedOption.fieldId !== field.id;

                    return (
                      <div key={field.id}>
                        <div
                          draggable={true}
                          onDragStart={handleDragStart(field.id, section.id)}
                          onDragOver={handleDragOver(field.id)}
                          onDragLeave={handleDragLeave}
                          onDrop={handleDrop(field.id, section.id)}
                          onDragEnd={handleDragEnd}
                          className={`
                            ${isDragOver && draggedField ? 'border-t-2 border-primary-500' : ''}
                            ${isDragOver && canAcceptOption ? 'border-2 border-green-500 bg-green-50' : ''}
                            ${isDragging ? 'opacity-50' : ''}
                          `}
                        >
                          <div className="flex items-stretch">
                            {/* Expand/collapse arrow for fields with options */}
                            {hasOptions && (
                              <button
                                className="px-1 hover:bg-gray-100 transition-colors flex items-center"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleField(field.id);
                                }}
                              >
                                <svg
                                  className={`w-3 h-3 text-gray-500 transition-transform ${
                                    isFieldExpanded ? 'transform rotate-90' : ''
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
                              </button>
                            )}
                            <button
                              ref={(el) => {
                                if (el) {
                                  fieldRefs.current.set(field.id, el);
                                } else {
                                  fieldRefs.current.delete(field.id);
                                }
                              }}
                              className={`flex-1 flex items-center gap-2 p-2 text-left text-sm hover:bg-gray-50 transition-colors cursor-move ${
                                isSelected ? 'bg-primary-50 border-l-2 border-primary-500' : ''
                              } ${!hasOptions ? 'pl-5' : ''}`}
                              onClick={() => onSelectField(field.id)}
                            >
                              {/* Drag handle icon */}
                              <svg className="w-3 h-3 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M7 2a2 2 0 00-2 2v12a2 2 0 002 2h6a2 2 0 002-2V4a2 2 0 00-2-2H7zm3 14a1 1 0 100-2 1 1 0 000 2zm0-4a1 1 0 100-2 1 1 0 000 2zm0-4a1 1 0 100-2 1 1 0 000 2z" />
                              </svg>
                              {getFieldIcon(status)}
                              <span className="flex-1 truncate text-gray-700 font-mono text-xs">
                                {field.id}
                              </span>
                              <span className="text-xs text-gray-400 font-mono">
                                [{field.type}]
                              </span>
                              {hasOptions && field.options && (
                                <span className="text-xs text-gray-500">
                                  ({field.options.length})
                                </span>
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Show options when expanded */}
                        {hasOptions && isFieldExpanded && field.options && (
                          <div className="ml-6 border-l-2 border-gray-200 bg-gray-50">
                            {field.options.map((option, idx) => {
                              const isOptionDragging = draggedOption?.fieldId === field.id && draggedOption?.optionIndex === idx;
                              
                              return (
                                <div
                                  key={`${field.id}-option-${idx}`}
                                  draggable={true}
                                  onDragStart={handleOptionDragStart(field.id, idx)}
                                  onDragEnd={handleDragEnd}
                                  className={`${isOptionDragging ? 'opacity-50' : ''}`}
                                >
                                  <button
                                    className={`w-full flex items-center gap-2 p-2 pl-4 text-left text-xs hover:bg-gray-100 transition-colors cursor-move ${
                                      selectedFieldId === `${field.id}:option:${idx}` ? 'bg-primary-50 border-l-2 border-primary-400' : ''
                                    }`}
                                    onClick={() => onSelectField(`${field.id}:option:${idx}`)}
                                    title={`Option ${idx + 1}: ${option.label || option.value}\nDrag to move to another field`}
                                  >
                                    {/* Drag handle for options */}
                                    <svg className="w-2 h-2 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                                      <path d="M7 2a2 2 0 00-2 2v12a2 2 0 002 2h6a2 2 0 002-2V4a2 2 0 00-2-2H7zm3 14a1 1 0 100-2 1 1 0 000 2zm0-4a1 1 0 100-2 1 1 0 000 2zm0-4a1 1 0 100-2 1 1 0 000 2z" />
                                    </svg>
                                    <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <circle cx="12" cy="12" r="3" strokeWidth="2" />
                                    </svg>
                                    <span className="flex-1 truncate text-gray-600">
                                      {option.label || option.value}
                                    </span>
                                    <span className="text-xs text-gray-400">
                                      #{idx + 1}
                                    </span>
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
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
              const isDragOver = dragOverField === field.id;
              const isDragging = draggedField?.fieldId === field.id;

              return (
                <div
                  key={field.id}
                  draggable={true}
                  onDragStart={handleDragStart(field.id, '_orphan')}
                  onDragOver={handleDragOver(field.id)}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop(field.id, '_orphan')}
                  onDragEnd={handleDragEnd}
                  className={`
                    ${isDragOver ? 'border-t-2 border-primary-500' : ''}
                    ${isDragging ? 'opacity-50' : ''}
                  `}
                >
                  <button
                    ref={(el) => {
                      if (el) {
                        fieldRefs.current.set(field.id, el);
                      } else {
                        fieldRefs.current.delete(field.id);
                      }
                    }}
                    className={`w-full flex items-center gap-2 p-2 text-left text-sm hover:bg-gray-50 transition-colors cursor-move ${
                      isSelected ? 'bg-primary-50 border-l-2 border-primary-500' : ''
                    }`}
                    onClick={() => onSelectField(field.id)}
                  >
                    {/* Drag handle icon */}
                    <svg className="w-3 h-3 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M7 2a2 2 0 00-2 2v12a2 2 0 002 2h6a2 2 0 002-2V4a2 2 0 00-2-2H7zm3 14a1 1 0 100-2 1 1 0 000 2zm0-4a1 1 0 100-2 1 1 0 000 2zm0-4a1 1 0 100-2 1 1 0 000 2z" />
                    </svg>
                    {getFieldIcon(status)}
                    <span className="flex-1 truncate text-gray-700 font-mono text-xs">
                      {field.id}
                    </span>
                    <span className="text-xs text-gray-400 font-mono">
                      [{field.type}]
                    </span>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
