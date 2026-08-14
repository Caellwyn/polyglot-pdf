import React from 'react';
import type { FormSchema, FormField } from '../types/schema';
import { GUIDANCE_STALE_RULE, currentIdentity, needsGuidanceAck, staleFieldIds }
  from '../utils/guidanceStaleness';
import { checkFieldComplete, safeOptions } from '../utils/validation';
import { getReview, isReviewTargetFromFindings, statusFromFindings }
  from '../utils/reviewStatus';
import { isFindingDismissable, ruleLabel, RULE_REMEDIES }
  from '../utils/lintFindings';
import { getIgnoredFields } from '../utils/ignoreField';
import { isGroupableField, mergeBlockReason } from '../utils/fieldGrouping';
import { isToReviewSection } from '../utils/sectionOps';
import type { LintFinding } from '../utils/remoteKitStore';

interface FieldListProps {
  schema: FormSchema;
  selectedFieldId: string | null;
  onSelectField: (fieldId: string) => void;
  // Escape-to-deselect (bd 92qe.5). Optional: the list works without it.
  onDeselect?: () => void;
  onReorderFields?: (sectionId: string, fieldIds: string[]) => void;
  onMoveOption?: (sourceFieldId: string, optionIndex: number, targetFieldId: string) => void;
  // Merge/group selection (bd polyglot-pdf-s4dp.1). groupSelection is the ordered
  // list of field ids ticked for a merge (first = primary). The merge controls
  // render only when these callbacks are wired.
  groupSelection?: string[];
  onToggleGroupSelection?: (fieldId: string) => void;
  onClearGroupSelection?: () => void;
  onMergeFields?: (kind: 'checkbox_group' | 'radio') => void;
  // Backend lint findings keyed by field id (lifted from the ValidationPanel's
  // report by App) so a flagged row can say WHY it is flagged right where the
  // author is looking, not only in the bottom strip (bd polyglot-pdf-0x10.6).
  lintFindingsByField?: Map<string, LintFinding[]>;
  // The loaded PDF's page count (bd polyglot-pdf-g63j). When present, a field
  // whose pdf_position claims a page outside 1..pageCount earns its own amber
  // reason instead of silently painting nowhere. Absent until the PDF loads.
  pageCount?: number;
  // Un-ignore a quarantined field (bd polyglot-pdf-mzkw). Absent -> the grey
  // Ignored bucket renders read-only.
  onRestoreField?: (fieldId: string) => void;
  // FORM-LEVEL findings (no field anchor) for the ONE pinned Form row at the
  // top of the list (sprint-18 C1, decision 1) -- already filtered of
  // dismissed WARNINGs by the host (visibleFormFindings).
  formFindings?: LintFinding[];
  // Standalone dismiss for a form-level WARNING -- the only standalone dismiss
  // in the editor; no field review can cover a schema-level finding.
  onDismissFormFinding?: (finding: LintFinding) => void;
  // "Show only fields needing review" (the strip count's secondary action) --
  // the overview that used to justify a separate warnings pane.
  reviewFilterActive?: boolean;
  onClearReviewFilter?: () => void;
}

export const FieldList: React.FC<FieldListProps> = ({
  schema,
  selectedFieldId,
  onSelectField,
  onDeselect,
  onReorderFields,
  onMoveOption,
  groupSelection = [],
  onToggleGroupSelection,
  onClearGroupSelection,
  onMergeFields,
  lintFindingsByField,
  pageCount,
  onRestoreField,
  formFindings,
  onDismissFormFinding,
  reviewFilterActive = false,
  onClearReviewFilter,
}) => {
  // Quarantined fields (bd mzkw): read from the stash, rendered in their own
  // grey group, and deliberately absent from every other list computation.
  const ignoredEntries = React.useMemo(() => getIgnoredFields(schema), [schema]);
  const [ignoredExpanded, setIgnoredExpanded] = React.useState(false);
  // The pinned Form row (sprint-18 C1): schema-level findings, collapsed to a
  // badge until opened. Auto-open whenever the ERROR count CHANGES to
  // non-zero -- an ERROR blocks the publish gate, so it must not hide behind
  // an unopened chevron. A user collapse holds only while the count is
  // unchanged: a NEW error re-opens the row (the once-per-lifetime latch this
  // replaces kept the row shut for every error after the first -- Opus outer
  // review, pass 1; the component is additionally keyed per form by App, so
  // the state never survives a kit switch).
  const [formRowExpanded, setFormRowExpanded] = React.useState(false);
  const formErrorCount = (formFindings ?? [])
    .filter(f => f.severity === 'ERROR').length;
  React.useEffect(() => {
    if (formErrorCount > 0) setFormRowExpanded(true);
  }, [formErrorCount]);
  // Grouping UI is active only when the parent wired the merge callbacks.
  const groupingEnabled = !!onToggleGroupSelection;
  const groupSelectionSet = React.useMemo(() => new Set(groupSelection), [groupSelection]);
  const [expandedSections, setExpandedSections] = React.useState<Set<string>>(
    new Set(schema.sections.map(s => s.id))
  );
  const [expandedFields, setExpandedFields] = React.useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = React.useState('');
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
    // While filtering (search OR the review filter), every section is
    // force-expanded so matches are visible; a chevron click must not
    // silently mutate the persisted expansion state (that would collapse a
    // section unexpectedly once the filter is cleared). The review filter
    // shares the guard (Opus outer review, pass 4): a collapsed section
    // hiding its own review targets under "Showing only fields needing
    // review" defeats the overview the filter exists to give.
    if (searchQuery.trim() || reviewFilterActive) return;
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

  // The row's effective status layers the human review sign-off over the
  // automatic derivation (bd polyglot-pdf-u8t6, amended by bd g63j): a real
  // ERROR always wins; otherwise needs_followup -> 'followup',
  // reviewed_correct -> 'complete' (green), and un-reviewed -> amber ALWAYS
  // (green is a human's word, never the machine's).
  // A field whose guidance drifted since it was authored cannot read green
  // until a human confirms the guidance still matches (bd polyglot-pdf-anim).
  // The BACKEND decides staleness (it wrote the hash); this reads its finding.
  const guidanceAckPending = (field: FormField) =>
    needsGuidanceAck(
      field,
      staleFieldIds(lintFindingsByField?.get(field.id)),
      currentIdentity(lintFindingsByField?.get(field.id), field.id),
    );

  // Routed through the SHARED helper (bd polyglot-pdf-l7u0) rather than
  // re-deriving the two booleans here: FieldOverlay paints from the same
  // function, so the canvas and this row cannot disagree about one field.
  const getFieldStatus = (field: FormField) =>
    statusFromFindings(field, lintFindingsByField?.get(field.id), pageCount);

  // Every reason a row is red, amber, or flagged, in plain language, for the
  // icon's tooltip: the human review state (sign-off / follow-up + its note)
  // first, then local completeness errors + review reasons + backend lint
  // findings. Empty for a settled-clean field with no findings.
  const getFieldMessages = (field: FormField): string[] => {
    const status = checkFieldComplete(field, pageCount);
    const lint = lintFindingsByField?.get(field.id) ?? [];
    const review = getReview(field);
    // Cap the note in the native tooltip: the editor's notes textarea is
    // uncapped, and a multi-KB note would make an unwieldy title (fresh-eyes).
    // The full note is always visible in the FieldEditor's Review box.
    const noteForTooltip = (n: string) =>
      n.length > 200 ? `${n.slice(0, 200)}...` : n;
    const reviewMessages: string[] = [];
    if (review.status === 'needs_followup') {
      reviewMessages.push(
        review.note ? `Needs follow-up: ${noteForTooltip(review.note)}` : 'Marked needs follow-up',
      );
    } else if (review.status === 'reviewed_correct') {
      // A signed-off field shows green -- unless un-acknowledged guidance
      // drift demotes it to amber (bd anim). Lead the tooltip with whichever
      // state the ICON shows, so its first line never contradicts an amber
      // clock sitting right next to it (Opus round 4); the sign-off (and any
      // note) still follows so the row never looks untouched.
      if (guidanceAckPending(field)) {
        reviewMessages.push(
          'Guidance changed after this field was reviewed -- confirm it '
          + 'still reads correctly (see Instructions)');
      }
      reviewMessages.push(
        review.note ? `Reviewed - correct: ${noteForTooltip(review.note)}` : 'Reviewed - correct',
      );
    } else if (review.note) {
      reviewMessages.push(`Note: ${noteForTooltip(review.note)}`);
    }
    return [
      ...reviewMessages,
      ...status.errors,
      ...status.reviewReasons,
      ...lint.map(f => f.message),
    ];
  };

  // The status icon, with the WHY on hover: a plain icon told the author a
  // field was broken but not what was wrong (bd polyglot-pdf-0x10.6).
  const renderStatusIcon = (field: FormField, status: string) => {
    const messages = getFieldMessages(field);
    return (
      <span
        title={messages.length > 0 ? messages.join('\n') : undefined}
        data-testid={`field-status-${field.id}`}
      >
        {getFieldIcon(status)}
      </span>
    );
  };

  // A visible per-row flag for backend findings (sprint-18 C1): the warnings
  // pane is gone, so the ROW is where a finding announces itself -- a count
  // chip (red when any ERROR, amber otherwise) beside the id, with the
  // messages on hover. Clicking the row opens the field, where each finding
  // renders at the property it concerns. The staleness rule is excluded to
  // MATCH the FieldEditor's chip (Opus round 2): its rendering is the ack
  // gate box + the amber status icon, and counting it here while the editor
  // chip omits it made the two surfaces disagree about the same field.
  const renderFindingBadge = (field: FormField) => {
    const findings = (lintFindingsByField?.get(field.id) ?? [])
      .filter(f => f.rule !== GUIDANCE_STALE_RULE);
    if (findings.length === 0) return null;
    const errors = findings.filter(f => f.severity === 'ERROR').length;
    return (
      <span
        data-testid={`field-flag-${field.id}`}
        className={`text-[10px] font-semibold rounded-full px-1.5 shrink-0 ${
          errors > 0 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
        }`}
        title={findings.map(f => f.message).join('\n')}
      >
        {findings.length}
      </span>
    );
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
    if (status === 'followup') {
      // Human-flagged "needs follow-up" (bd polyglot-pdf-u8t6): a flag icon, in
      // amber to sit in the same needs-attention band as the auto-review clock
      // but visibly distinct (a deliberate human flag, not a machine guess).
      return (
        <svg className="w-4 h-4 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M3 3a1 1 0 011-1h11.5a1 1 0 01.8 1.6L13.75 7l3.55 3.4a1 1 0 01-.8 1.6H5v6a1 1 0 11-2 0V3z"
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

  // Filter predicate: matches a field by id / spoken_name / pdf_field_name.
  // An empty/whitespace query matches everything (full list restored).
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const matchesQuery = React.useCallback(
    (field: FormField) => {
      if (!normalizedQuery) return true;
      const haystacks = [field.id, field.spoken_name, field.pdf_field_name];
      return haystacks.some(
        h => h != null && h.toLowerCase().includes(normalizedQuery)
      );
    },
    [normalizedQuery]
  );

  // The search filter, composed with the review filter (sprint-18 C1): the
  // strip count's secondary action narrows the list to review targets -- the
  // same predicate the count and the jump use, so "N to review" and the
  // filtered list always show the same fields.
  const passesFilters = React.useCallback(
    (field: FormField) => {
      if (!matchesQuery(field)) return false;
      if (reviewFilterActive
          && !isReviewTargetFromFindings(field, lintFindingsByField?.get(field.id))) {
        return false;
      }
      return true;
    },
    [matchesQuery, reviewFilterActive, lintFindingsByField],
  );

  // Group fields by section, applying the filters while keeping grouping.
  const sectionedFields = React.useMemo(() => {
    const map = new Map<string, FormField[]>();

    for (const section of schema.sections) {
      const fields = section.fields
        .map(id => fieldsById.get(id))
        .filter((f): f is FormField => f !== undefined)
        .filter(passesFilters);
      map.set(section.id, fields);
    }

    // Fields without section
    const orphanFields = schema.fields.filter(f => !f.section_id).filter(passesFilters);
    if (orphanFields.length > 0) {
      map.set('_orphan', orphanFields);
    }

    return map;
  }, [schema.sections, schema.fields, fieldsById, passesFilters]);

  // Sections that contain at least one matching field while filtering.
  const matchingSectionCount = React.useMemo(() => {
    if (!normalizedQuery) return schema.sections.length;
    return schema.sections.filter(s => (sectionedFields.get(s.id) || []).length > 0).length;
  }, [normalizedQuery, schema.sections, sectionedFields]);

  // The visible fields in reading order: sections as listed, then orphans --
  // exactly what the list renders (search filter applied). Drives the
  // next-needs-review jump and arrow-key navigation (bd 92qe.5).
  const visibleOrderedFields = React.useMemo(() => {
    const ordered: FormField[] = [];
    for (const section of schema.sections) {
      ordered.push(...(sectionedFields.get(section.id) || []));
    }
    ordered.push(...(sectionedFields.get('_orphan') || []));
    return ordered;
  }, [schema.sections, sectionedFields]);

  // Option rows select as "<fieldId>:option:<n>" -- resolve to the base field
  // so navigation starts from the right position.
  const selectedBaseId = selectedFieldId ? selectedFieldId.split(':option:')[0] : null;

  // Anything left to review? Drives the button's disabled state so a finished
  // form reads as DONE instead of a silently dead button (fresh-eyes note).
  // A field signed off as reviewed_correct is NOT a target; a needs_followup
  // field IS one (bd polyglot-pdf-u8t6) -- both flow through isReviewTarget's
  // effective-status precedence.
  const hasReviewTarget = React.useMemo(
    // Routed through the SAME findings-driven predicate the strip's counts use
    // (sprint-18 C1, decision 2): the jump, the count, and the icons must
    // never disagree about whether a field still needs review.
    () => visibleOrderedFields.some(
      f => isReviewTargetFromFindings(f, lintFindingsByField?.get(f.id))),
    [visibleOrderedFields, lintFindingsByField]
  );

  const jumpToNextReview = React.useCallback(() => {
    const fields = visibleOrderedFields;
    if (fields.length === 0) return;
    const current = selectedBaseId
      ? fields.findIndex(f => f.id === selectedBaseId)
      : -1;
    for (let step = 1; step <= fields.length; step++) {
      const candidate = fields[(current + step) % fields.length];
      if (isReviewTargetFromFindings(
            candidate, lintFindingsByField?.get(candidate.id))) {
        onSelectField(candidate.id);
        return;
      }
    }
    // Everything visible is complete -> nothing to jump to.
  }, [visibleOrderedFields, selectedBaseId, onSelectField, lintFindingsByField]);

  const moveSelection = React.useCallback(
    (delta: 1 | -1) => {
      const fields = visibleOrderedFields;
      if (fields.length === 0) return;
      const current = selectedBaseId
        ? fields.findIndex(f => f.id === selectedBaseId)
        : -1;
      let next: number;
      if (current === -1) {
        next = delta === 1 ? 0 : fields.length - 1;
      } else {
        next = Math.min(fields.length - 1, Math.max(0, current + delta));
      }
      if (next !== current) onSelectField(fields[next].id);
    },
    [visibleOrderedFields, selectedBaseId, onSelectField]
  );

  // Keyboard navigation: N = next needing review, arrows move selection,
  // Escape deselects. Never fires while typing in an editable control.
  React.useEffect(() => {
    const isEditable = (el: EventTarget | null) => {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      return (
        tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
      );
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      if (isEditable(e.target)) return;
      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        jumpToNextReview();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveSelection(1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveSelection(-1);
      } else if (e.key === 'Escape' && onDeselect) {
        onDeselect();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [jumpToNextReview, moveSelection, onDeselect]);

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

  const isFiltering = normalizedQuery.length > 0;
  const hasAnyMatch = matchingSectionCount > 0 || (sectionedFields.get('_orphan') || []).length > 0;

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Search / filter box + review navigation */}
      <div className="p-2 border-b border-gray-200 bg-gray-50 flex items-center gap-2">
        <div className="relative flex-1">
          <svg
            className="w-4 h-4 text-gray-400 absolute left-2 top-1/2 -translate-y-1/2 pointer-events-none"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-4.35-4.35M11 18a7 7 0 100-14 7 7 0 000 14z"
            />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search fields..."
            aria-label="Search fields"
            className="w-full pl-8 pr-8 py-1.5 text-sm rounded-md border border-gray-300 bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={jumpToNextReview}
          disabled={!hasReviewTarget}
          title={hasReviewTarget
            ? 'Jump to the next field needing attention (N). Arrow keys move; Esc deselects.'
            : 'Every visible field is reviewed -- nothing left to review.'}
          className="shrink-0 px-2 py-1.5 text-xs font-medium rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-default"
        >
          Next to review
        </button>
      </div>

      {/* Merge action bar (bd polyglot-pdf-s4dp.1): appears once 2+ groupable
          fields are ticked. Merges them into one consolidated options[] field.
          The Merge button is disabled (with an explanation) when the selection
          can't be merged -- too few, spanning sections, or missing a PDF mapping
          (Codex PR #256). */}
      {groupingEnabled && groupSelection.length > 0 && (() => {
        const reason = mergeBlockReason(schema, groupSelection);
        const reasonText =
          reason === 'too-few' ? 'Select 2 or more radio/checkbox fields to merge'
          : reason === 'cross-section' ? 'Selected fields span multiple sections -- merge within one section'
          : reason === 'missing-pdf-name' ? 'A selected field has no PDF mapping and cannot be merged'
          : 'Merge selected fields into one options field';
        return (
        <div className="p-2 border-b border-gray-200 bg-primary-50 flex items-center gap-2">
          <span className="text-xs text-gray-700 flex-1">
            {groupSelection.length} field{groupSelection.length === 1 ? '' : 's'} selected to merge
            {reason && reason !== 'too-few' && (
              <span className="block text-amber-700">{reasonText}</span>
            )}
          </span>
          <button
            type="button"
            className="btn-sm btn-primary disabled:opacity-50"
            disabled={reason !== null}
            onClick={() => onMergeFields?.('checkbox_group')}
            title="Several boxes can be checked at once (multi-select checkbox group)"
          >
            Merge (several)
          </button>
          <button
            type="button"
            className="btn-sm btn-primary disabled:opacity-50"
            disabled={reason !== null}
            onClick={() => onMergeFields?.('radio')}
            title="Exactly one box is checked (single-select radio group)"
          >
            Merge (exactly one)
          </button>
          <button
            type="button"
            className="btn-sm btn-secondary"
            onClick={() => onClearGroupSelection?.()}
          >
            Clear
          </button>
        </div>
        );
      })()}

      <div className="flex-1 overflow-auto custom-scrollbar">
      <div className="p-2 space-y-1">
        {/* Review-filter note (sprint-18 C1): the list is narrowed to review
            targets by the strip count's secondary action; say so, with the
            way back. */}
        {reviewFilterActive && (
          <div
            className="flex items-center gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1"
            role="status"
            data-testid="review-filter-note"
          >
            <span className="flex-1">Showing only fields needing review.</span>
            {onClearReviewFilter && (
              <button
                type="button"
                className="underline"
                onClick={onClearReviewFilter}
              >
                Show all
              </button>
            )}
          </div>
        )}

        {/* The ONE pinned Form row (sprint-18 C1, decision 1): findings about
            the FORM rather than any field -- schema-wide coverage, kit-level
            flags, PDF widget claims. No field review can cover these, so this
            row is the only place a standalone dismiss exists (WARNINGs only;
            an ERROR blocks the publish gate and cannot be waved away). */}
        {(formFindings ?? []).length > 0 && (() => {
          const findings = formFindings ?? [];
          const warnCount = findings.length - formErrorCount;
          return (
            <div
              className={`rounded-md shadow-sm border ${
                formErrorCount > 0
                  ? 'bg-red-50 border-red-300'
                  : 'bg-amber-50 border-amber-300'
              }`}
              data-testid="form-findings-row"
            >
              <button
                className="w-full flex items-center gap-2 p-2 text-left"
                onClick={() => setFormRowExpanded(v => !v)}
                aria-expanded={formRowExpanded}
              >
                <svg
                  className={`w-4 h-4 text-gray-500 transition-transform ${
                    formRowExpanded ? 'transform rotate-90' : ''
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
                <span className={`text-sm font-medium flex-1 ${
                  formErrorCount > 0 ? 'text-red-900' : 'text-amber-900'
                }`}>
                  Form
                </span>
                {formErrorCount > 0 && (
                  <span className="text-[10px] font-semibold rounded-full px-1.5 bg-red-100 text-red-700">
                    {formErrorCount} to fix
                  </span>
                )}
                {warnCount > 0 && (
                  <span className="text-[10px] font-semibold rounded-full px-1.5 bg-amber-100 text-amber-700">
                    {warnCount} notice{warnCount !== 1 ? 's' : ''}
                  </span>
                )}
              </button>
              {formRowExpanded && (
                <div className="border-t border-gray-200 divide-y divide-gray-100">
                  {findings.map((finding, idx) => {
                    const isError = finding.severity === 'ERROR';
                    const label = ruleLabel(finding.rule);
                    const remedy = finding.rule
                      ? RULE_REMEDIES[finding.rule]
                      : undefined;
                    return (
                      <div
                        key={`${finding.rule}|${finding.path}|${idx}`}
                        className="p-2 text-xs space-y-0.5"
                        data-testid={`form-finding-${idx}`}
                      >
                        <div className={isError ? 'text-red-700' : 'text-amber-800'}>
                          {label && <span className="font-medium">{label}: </span>}
                          {finding.message}
                        </div>
                        {remedy && (
                          <div className="text-gray-600">{remedy}</div>
                        )}
                        {onDismissFormFinding && isFindingDismissable(finding) && (
                          <button
                            type="button"
                            className="text-gray-500 underline"
                            data-testid={`dismiss-form-finding-${idx}`}
                            title="Hide this notice for this form. It returns if the underlying finding changes."
                            onClick={() => onDismissFormFinding(finding)}
                          >
                            Dismiss
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })()}

        {/* Render sections */}
        {schema.sections.map(section => {
          const fields = sectionedFields.get(section.id) || [];
          // While filtering (search or review filter), hide empty sections
          // and force-expand the rest -- a stale collapse must not hide the
          // filter's own targets (Opus outer review, pass 4).
          const filtering = isFiltering || reviewFilterActive;
          if (filtering && fields.length === 0) return null;
          const isExpanded = filtering || expandedSections.has(section.id);
          // Total resolved fields in this section, independent of the filter
          // (matches the non-filtered count badge so it does not jump on clear).
          const totalFieldCount = section.fields.filter(id => fieldsById.has(id)).length;

          // A 'To review' section (bd polyglot-pdf-6cfu.3): the deterministic
          // derivation could not confidently place these fields; a human must
          // re-file each before the form can be marked complete (the
          // to-review-pending lint rule blocks the publish gate). Highlight
          // it amber while it still holds fields -- by its fields[] listing
          // OR by fields pointing at it via section_id (the lint gate keys
          // on the latter; a drifted kit must never block invisibly).
          const needsReview = isToReviewSection(section.id)
            && (totalFieldCount > 0
                || schema.fields.some(f => f.section_id === section.id));

          return (
            <div
              key={section.id}
              className={`rounded-md shadow-sm ${
                needsReview ? 'bg-amber-50 border border-amber-400' : 'bg-white'
              }`}
            >
              {/* Section Header */}
              <button
                className={`w-full flex items-center gap-2 p-2 text-left transition-colors ${
                  filtering ? 'cursor-default'
                    : needsReview ? 'hover:bg-amber-100' : 'hover:bg-gray-50'
                }`}
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
                <span className={`text-sm font-medium flex-1 ${
                  needsReview ? 'text-amber-900' : 'text-gray-700'
                }`}>
                  {section.label}
                </span>
                {needsReview && (
                  <span className="text-xs font-medium text-amber-800 bg-amber-100 border border-amber-300 rounded px-1.5 py-0.5">
                    re-file required
                  </span>
                )}
                <span className="text-xs text-gray-500">
                  {filtering ? `(${fields.length}/${totalFieldCount})` : `(${totalFieldCount})`}
                </span>
              </button>

              {/* Fields */}
              {isExpanded && (
                <div className="border-t border-gray-100">
                  {fields.map(field => {
                    const status = getFieldStatus(field);
                    const isSelected = field.id === selectedFieldId;
                    const isDragOver = dragOverField === field.id;
                    const isDragging = draggedField?.fieldId === field.id;
                    // safeOptions (bd polyglot-pdf-8bjdx): a truthy non-array
                    // `options` (or one carrying null entries) passes a bare
                    // `.length > 0` check and then throws out of the `.map`
                    // below, blanking the WHOLE field list rather than one row.
                    const safeOpts = safeOptions(field);
                    const hasOptions = safeOpts.length > 0;
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
                            {/* Merge checkbox (bd polyglot-pdf-s4dp.1): only
                                groupable (radio/checkbox) fields can be ticked
                                into a merge group. */}
                            {groupingEnabled && isGroupableField(field) && (
                              <label
                                className="px-1 flex items-center cursor-pointer"
                                title="Select to merge with other radio/checkbox fields"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  className="rounded"
                                  checked={groupSelectionSet.has(field.id)}
                                  onChange={() => onToggleGroupSelection?.(field.id)}
                                  aria-label={`Select ${field.id} for merge`}
                                />
                              </label>
                            )}
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
                              {renderStatusIcon(field, status)}
                              <span className="flex-1 truncate text-gray-700 font-mono text-xs">
                                {field.id}
                              </span>
                              {renderFindingBadge(field)}
                              <span className="text-xs text-gray-400 font-mono">
                                [{field.type}]
                              </span>
                              {hasOptions && (
                                <span className="text-xs text-gray-500">
                                  ({safeOpts.length})
                                </span>
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Show options when expanded */}
                        {hasOptions && isFieldExpanded && (
                          <div className="ml-6 border-l-2 border-gray-200 bg-gray-50">
                            {safeOpts.map((option, idx) => {
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
                    {renderStatusIcon(field, status)}
                    <span className="flex-1 truncate text-gray-700 font-mono text-xs">
                      {field.id}
                    </span>
                    {renderFindingBadge(field)}
                    <span className="text-xs text-gray-400 font-mono">
                      [{field.type}]
                    </span>
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Ignored (grey) bucket -- quarantined fields (bd polyglot-pdf-mzkw).
            Sourced from the _ignored_fields stash, NOT from schema.fields, so
            these rows are deliberately outside visibleOrderedFields: the review
            jump never stops on them and they count toward nothing. They stay
            VISIBLE (and un-ignorable in one click) precisely because ignoring
            is reversible -- an invisible escape hatch would be a delete. */}
        {ignoredEntries.length > 0 && (
          <div className="bg-white rounded-md shadow-sm opacity-75">
            <button
              className="w-full flex items-center gap-2 p-2 text-left hover:bg-gray-50 transition-colors"
              onClick={() => setIgnoredExpanded(v => !v)}
              aria-expanded={ignoredExpanded}
            >
              <svg
                className={`w-4 h-4 text-gray-500 transition-transform ${
                  ignoredExpanded ? 'transform rotate-90' : ''
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
              <span className="text-sm font-medium flex-1 text-gray-500">
                Ignored -- not on this form
              </span>
              <span className="text-xs text-gray-400">({ignoredEntries.length})</span>
            </button>
            {ignoredExpanded && (
              <div className="border-t border-gray-100">
                {ignoredEntries.map(entry => (
                  <div
                    key={entry.field.id}
                    className="flex items-center gap-2 p-2 pl-5 text-sm"
                    data-testid={`ignored-row-${entry.field.id}`}
                  >
                    <span
                      title={entry.field._review?.note
                        ? `Ignored: ${entry.field._review.note}`
                        : 'Ignored -- set aside, not deleted'}
                      data-testid={`field-status-${entry.field.id}`}
                    >
                      {/* Grey status dot: parked, neither done nor broken. */}
                      <svg className="w-4 h-4 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          fillRule="evenodd"
                          d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </span>
                    <span className="flex-1 truncate text-gray-500 font-mono text-xs">
                      {entry.field.id}
                    </span>
                    {onRestoreField && (
                      <button
                        type="button"
                        className="btn-sm btn-secondary"
                        onClick={() => onRestoreField(entry.field.id)}
                        title="Bring this field back to its original place"
                      >
                        Un-ignore
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* No-results state while filtering */}
        {isFiltering && !hasAnyMatch && (
          <div className="p-4 text-center text-sm text-gray-500">
            No fields match "{searchQuery.trim()}".
          </div>
        )}
      </div>
      </div>
    </div>
  );
};
