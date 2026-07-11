// Section management panel (bd polyglot-pdf-6cfu.3).
//
// A modal over the editor offering the manual division operations the
// deterministic derivation cannot decide for a human: add / rename / merge /
// remove sections, plus the hosted-author "Regenerate divisions" action.
// Every mutation is computed by the pure ops in utils/sectionOps and handed
// to App via onApply as ONE atomic {fields, sections, parts} commit (one
// undo step). 'To review' sections (the sec_to_review id prefix minted by
// the derivation for fields a human must re-file) are highlighted; merging
// one into a real section is the workflow that empties it and satisfies the
// publish gate.

import React from 'react';
import type { FormField, FormPart, FormSection } from '../types/schema';
import {
  addSection,
  isToReviewSection,
  mergeSections,
  movedFieldCount,
  removeSection,
  renameSection,
  type DivisionsPatch,
} from '../utils/sectionOps';

interface SectionManagerProps {
  fields: FormField[];
  sections: FormSection[];
  parts?: FormPart[];
  /** hosted + author + an open kit: shows the Regenerate divisions action. */
  canRegenerate: boolean;
  onApply: (patch: DivisionsPatch) => void;
  onRegenerate: () => void;
  onClose: () => void;
}

export const SectionManager: React.FC<SectionManagerProps> = ({
  fields, sections, parts, canRegenerate, onApply, onRegenerate, onClose,
}) => {
  const [newLabel, setNewLabel] = React.useState('');

  const fieldCount = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of fields) {
      if (f.section_id) counts.set(f.section_id, (counts.get(f.section_id) ?? 0) + 1);
    }
    return counts;
  }, [fields]);

  const handleRename = (sectionId: string, label: string, prev: string) => {
    if (label.trim() && label.trim() !== prev) {
      onApply(renameSection(fields, sections, parts, sectionId, label));
    }
  };

  const handleMerge = (sourceId: string, targetId: string) => {
    if (!targetId) return;
    const source = sections.find(s => s.id === sourceId);
    const target = sections.find(s => s.id === targetId);
    if (!source || !target) return;
    // Count what removeSection will ACTUALLY move (field.section_id is
    // authoritative), so the confirm text matches the row badge even on a
    // kit carrying fields[]-vs-section_id drift (bd polyglot-pdf-w7rg).
    const n = movedFieldCount(fields, sourceId);
    const ok = window.confirm(
      `Merge "${source.label}" into "${target.label}"? Its ${n} ` +
      `field(s) move to "${target.label}" and the section is removed.`
    );
    if (ok) onApply(mergeSections(fields, sections, parts, sourceId, targetId));
  };

  const handleRemove = (sectionId: string) => {
    const section = sections.find(s => s.id === sectionId);
    if (!section) return;
    const n = movedFieldCount(fields, sectionId);
    const ok = window.confirm(
      n > 0
        ? `Remove "${section.label}"? Its ${n} field(s) become Uncategorized ` +
          `(use Merge instead to re-file them into another section).`
        : `Remove the empty section "${section.label}"?`
    );
    if (ok) onApply(removeSection(fields, sections, parts, sectionId, null));
  };

  const handleAdd = () => {
    if (!newLabel.trim()) return;
    onApply(addSection(fields, sections, parts, newLabel));
    setNewLabel('');
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Manage sections"
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">Manage sections</h2>
          <div className="flex items-center gap-2">
            {canRegenerate && (
              <button
                className="px-3 py-1.5 text-sm rounded-md border border-red-300 text-red-700 hover:bg-red-50"
                onClick={onRegenerate}
              >
                Regenerate divisions
              </button>
            )}
            <button
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-2">
          {sections.map(section => {
            const toReview = isToReviewSection(section.id);
            const count = fieldCount.get(section.id) ?? section.fields.length;
            return (
              <div
                key={section.id}
                className={`flex items-center gap-2 p-2 rounded-md border ${
                  toReview && count > 0
                    ? 'border-amber-400 bg-amber-50'
                    : 'border-gray-200'
                }`}
              >
                <input
                  className="flex-1 min-w-0 px-2 py-1 text-sm border border-transparent rounded hover:border-gray-300 focus:border-blue-400 focus:outline-none bg-transparent"
                  defaultValue={section.label}
                  aria-label={`Rename ${section.label}`}
                  onBlur={e => handleRename(section.id, e.target.value, section.label)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                  }}
                />
                {toReview && count > 0 && (
                  <span className="shrink-0 text-xs font-medium text-amber-800 bg-amber-100 border border-amber-300 rounded px-1.5 py-0.5">
                    re-file required
                  </span>
                )}
                <span className="shrink-0 text-xs text-gray-500 w-14 text-right">
                  {count} field{count === 1 ? '' : 's'}
                </span>
                <select
                  className="shrink-0 text-xs border border-gray-300 rounded px-1 py-1 text-gray-700"
                  value=""
                  aria-label={`Merge ${section.label} into`}
                  onChange={e => handleMerge(section.id, e.target.value)}
                >
                  <option value="">Merge into...</option>
                  {sections
                    .filter(s => s.id !== section.id)
                    .map(s => (
                      <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                </select>
                <button
                  className="shrink-0 text-xs px-2 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
                  onClick={() => handleRemove(section.id)}
                  aria-label={`Remove ${section.label}`}
                >
                  Remove
                </button>
              </div>
            );
          })}
          {sections.length === 0 && (
            <p className="text-sm text-gray-500">No sections yet.</p>
          )}
        </div>

        <div className="flex items-center gap-2 p-4 border-t border-gray-200">
          <input
            className="flex-1 px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:border-blue-400 focus:outline-none"
            placeholder="New section label"
            value={newLabel}
            aria-label="New section label"
            onChange={e => setNewLabel(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd(); }}
          />
          <button
            className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            onClick={handleAdd}
            disabled={!newLabel.trim()}
          >
            Add section
          </button>
        </div>
      </div>
    </div>
  );
};
