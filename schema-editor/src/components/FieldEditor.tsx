import React from 'react';
import type {
  FormField,
  FieldType,
  FormSchema,
  FormSection,
} from '../types/schema';
import {
  changeGroupKindBlockReason,
  canUngroup,
  mintOptionSlug,
  mintUniqueSlugs,
  optionValueReferencedBy,
  retargetOptionValueReferences,
} from '../utils/fieldGrouping';
import { ConditionBuilder } from './ConditionBuilder';
import { moveFieldToSection } from '../utils/sectionOps';
import {
  checkFieldComplete, hasCondition, safeOptions, safeOptionsPreservingArity,
} from '../utils/validation';
import { getReview, newFindingsSinceReview, withGuidanceAck, withReviewNote,
  withReviewStatus } from '../utils/reviewStatus';
import { GUIDANCE_STALE_RULE, currentIdentity, isAcknowledged }
  from '../utils/guidanceStaleness';
import { propertyAnchor, resolveOptionIndex, ruleLabel, RULE_REMEDIES }
  from '../utils/lintFindings';
import type { FieldReviewStatus } from '../types/schema';
import type { LintFinding, UnclaimedWidget } from '../utils/remoteKitStore';

interface FieldEditorProps {
  field: FormField | null;
  schema: FormSchema;
  onUpdateField: (field: FormField) => void;
  // Rename the field's internal id, retargeting every in-schema reference in
  // one undoable commit (bd polyglot-pdf-0x10.1). Returns a human-readable
  // block reason (shown inline) or null on success. Optional: without it the
  // id header stays read-only.
  onRenameField?: (oldId: string, newId: string) => string | null;
  // Un-merge a consolidated options[] field back into separate per-widget fields
  // (bd polyglot-pdf-s4dp.1). Optional so the editor still renders without it.
  onUnmergeField?: (fieldId: string) => void;
  // Flip an existing consolidated group between checkbox_group (multi-select)
  // and radio (single-select) in place (bd polyglot-pdf-checkbox-radio). A group
  // extracted as the wrong kind otherwise has no reachable path to the other kind
  // (the Field Type picker is read-only for a group, and Merge only offers the
  // kind choice when combining loose widgets). Optional so the editor still
  // renders without it (the control is simply not shown).
  onChangeGroupKind?: (fieldId: string, kind: 'checkbox_group' | 'radio') => void;
  // Commit a schema-wide field list (and optionally sections), e.g. after
  // retargeting dependents' show_if / require_if to an option's
  // freshly-renamed slug (bd polyglot-pdf-432u, extended to sections by bd
  // polyglot-pdf-6b7z -- a section's show_if can equally reference a renamed
  // option slug). Separate from onUpdateField, which can only patch the
  // SINGLE field being edited -- a rename can touch OTHER fields'/sections'
  // conditions too. Optional so the editor still renders without it (falls
  // back to leaving dependents unretargeted, same as before this fix).
  onUpdateFields?: (fields: FormField[], sections?: FormSection[]) => void;
  // Update form-level metadata (version/edition/OMB/expiration -- bd
  // polyglot-pdf-s4dp.2). Optional; when absent the metadata panel is read-only.
  onUpdateMetadata?: (patch: Partial<FormSchema['form_metadata']>) => void;
  // Author-tier surfaces (bd h76m.10): per-option PDF-widget mapping lives
  // under an Advanced disclosure only authors see. Editor-tier contractors see
  // the option value as a read-only chip but not the widget plumbing. Defaults
  // true so local (non-hosted) editing is full author tier.
  authorTier?: boolean;
  // "Add from PDF widgets" picker (bd polyglot-pdf-nivy, P5.3c): fetch the kit's
  // unclaimed PDF button widgets so the author can add a missed checkbox/radio
  // box to a group. Optional -- provided only in hosted author mode on an open
  // kit; when absent the picker is not offered (local mode has no backend dump).
  onLoadUnclaimedWidgets?: () => Promise<UnclaimedWidget[]>;
  // Backend lint findings anchored to THIS field (lifted from the strip's
  // report by App), rendered at the PROPERTY each one names -- Instructions,
  // an option row, the condition builders -- with the banner as the home for
  // the field-anchored residue (sprint-18 C1; formerly all-banner, bd
  // polyglot-pdf-0x10.6).
  lintFindings?: LintFinding[];
  // The loaded PDF's page count (bd polyglot-pdf-g63j) so the flagged-reasons
  // banner can name a field claiming a page the document does not have.
  pageCount?: number;
  // Quarantine this field (bd polyglot-pdf-mzkw). Returns a block reason to
  // display, or null on success. Absent -> the Ignored option is not offered.
  onIgnoreField?: (fieldId: string) => string | null;
  // Why ignoring is currently refused for the selected field, or null when it
  // is allowed (computed by App, which owns the whole schema).
  ignoreBlocked?: string | null;
  // Re-author THIS field's guidance from the form's instruction booklet (bd
  // polyglot-pdf-cpiw) -- the costly half of the staleness gate, offered right
  // where the gate is raised so a reviewer does not have to hand-copy prose out
  // of the booklet. Rewrites the STORED schema server-side, so App reloads the
  // kit afterwards. Optional: absent without a backend + author tier + open kit.
  // Resolves TRUE when the guidance actually changed -- false means the rewrite
  // ran but wrote nothing (judge unavailable, hand-edited guidance the route
  // never clobbers, or the booklet had nothing for this field), which the
  // button explains rather than looking like success.
  onRegenerateGuidance?: (fieldId: string) => Promise<boolean>;
}

// Editable field-id header (bd polyglot-pdf-0x10.1). The id is the schema's
// join key, so it renames through an explicit edit mode (pencil -> input ->
// Enter/check commits, Escape/x cancels) rather than a live-typing input; the
// commit routes through onRenameField, which retargets every in-schema
// reference atomically and returns a block reason (shown inline) when the id
// is empty/duplicate/not-a-slug.
const FieldIdHeader: React.FC<{
  fieldId: string;
  onRenameField: (oldId: string, newId: string) => string | null;
}> = ({ fieldId, onRenameField }) => {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(fieldId);
  const [error, setError] = React.useState<string | null>(null);

  const start = () => {
    setDraft(fieldId);
    setError(null);
    setEditing(true);
  };
  const cancel = () => {
    setEditing(false);
    setError(null);
  };
  const commit = () => {
    const reason = onRenameField(fieldId, draft);
    if (reason) {
      setError(reason);
      return;
    }
    setEditing(false);
    setError(null);
  };

  if (!editing) {
    return (
      <div className="flex items-center gap-2">
        <h3 className="text-lg font-semibold text-gray-900">{fieldId}</h3>
        <button
          type="button"
          className="text-gray-400 hover:text-gray-700"
          title="Rename this field's internal ID (updates every reference to it)"
          aria-label="Rename field ID"
          onClick={start}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
            />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <input
          type="text"
          className="input flex-1 font-mono text-sm"
          value={draft}
          autoFocus
          aria-label="Field ID"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') cancel();
          }}
        />
        <button type="button" className="btn-sm btn-primary" onClick={commit}>
          Rename
        </button>
        <button type="button" className="btn-sm btn-secondary" onClick={cancel}>
          Cancel
        </button>
      </div>
      {error && (
        <p className="text-xs text-red-600" role="alert">{error}</p>
      )}
      <p className="text-xs text-gray-500">
        Renaming updates every condition, section and copy that references this field.
      </p>
    </div>
  );
};

// The editable form-metadata panel (bd polyglot-pdf-s4dp.2). Shown when no field
// is selected, so a human can correct an auto-extracted version -- or fill one a
// version-less form lacked (version defaults to "unknown", never blank). Each
// input commits a single-key patch through onUpdateMetadata.
const FormMetadataEditor: React.FC<{
  schema: FormSchema;
  onUpdateMetadata?: (patch: Partial<FormSchema['form_metadata']>) => void;
}> = ({ schema, onUpdateMetadata }) => {
  const meta = schema.form_metadata;
  const set = (key: keyof FormSchema['form_metadata']) => (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const raw = e.target.value;
    // `version` is REQUIRED on the schema: clearing it must degrade to the
    // "unknown" sentinel, never undefined -- a save serializes with JSON.stringify
    // which drops undefined keys, which would strip the required field and fail
    // backend validation (Codex PR #263). Optional fields clear to undefined.
    const value = key === 'version' ? (raw || 'unknown') : (raw || undefined);
    const patch = { [key]: value } as Partial<FormSchema['form_metadata']>;
    // A MANUAL version edit makes the stale auto-extracted version_confidence
    // meaningless -- leaving the old 0/0.4 would keep the "(verify)" hint with no
    // way to clear it. Clear it on any non-empty version edit (a human-entered
    // version is authoritative); a cleared-to-"unknown" version keeps low
    // confidence via the "unknown" branch of the lowConfidence check (Codex r2).
    if (key === 'version') {
      patch.version_confidence = raw ? undefined : 0;
    }
    onUpdateMetadata?.(patch);
  };
  const lowConfidence =
    meta?.version === 'unknown' ||
    (typeof meta?.version_confidence === 'number' && meta.version_confidence <= 0.5);

  const rows: { key: keyof FormSchema['form_metadata']; label: string; placeholder: string }[] = [
    { key: 'version', label: 'Version / Revision', placeholder: 'e.g., December 2024 or 01/20/25' },
    { key: 'edition_date', label: 'Edition date', placeholder: 'e.g., 01/20/25' },
    { key: 'omb_number', label: 'OMB number', placeholder: 'e.g., 1615-0082' },
    { key: 'expiration_date', label: 'Expiration date', placeholder: 'e.g., 02/28/2027' },
  ];

  return (
    <div className="h-full overflow-auto custom-scrollbar">
      <div className="p-4 space-y-4">
        <div className="border-b border-gray-200 pb-3">
          <h3 className="text-lg font-semibold text-gray-900">Form metadata</h3>
          <p className="text-sm text-gray-500">{meta?.form_number || meta?.title || 'Form'}</p>
        </div>

        {lowConfidence && (
          <div className="text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded p-2">
            The form version could not be confidently detected -- please verify and
            correct it below.
          </div>
        )}

        {rows.map(({ key, label, placeholder }) => (
          <div key={key}>
            <label className="label">{label}</label>
            <input
              type="text"
              className="input"
              aria-label={label}
              value={(meta?.[key] as string) ?? ''}
              onChange={set(key)}
              placeholder={placeholder}
              disabled={!onUpdateMetadata}
            />
          </div>
        ))}

        <p className="text-xs text-gray-400">
          Select a field on the left to edit its properties.
        </p>
      </div>
    </div>
  );
};

// Findings rendered AT the property they concern (sprint-18 C1, decision 1):
// the warnings pane is gone, so a finding about the Instructions box, an
// option row, or a condition renders directly under that control -- label,
// plain message, and the imperative remedy line (RULE_REMEDIES, authored by
// the C12 copy pass for exactly this surface).
const EmbeddedFindings: React.FC<{
  findings: LintFinding[];
  anchor: string;
}> = ({ findings, anchor }) => {
  if (findings.length === 0) return null;
  const hasError = findings.some(f => f.severity === 'ERROR');
  return (
    <div
      className={`mt-1 rounded-md border p-2 space-y-1 ${
        hasError ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'
      }`}
      role="alert"
      data-embedded-finding={anchor}
      data-testid={`embedded-findings-${anchor}`}
    >
      {findings.map((f, i) => {
        const label = ruleLabel(f.rule);
        const remedy = f.rule ? RULE_REMEDIES[f.rule] : undefined;
        return (
          <div key={`${f.rule}|${f.path}|${i}`} className="text-xs space-y-0.5">
            <div className={f.severity === 'ERROR' ? 'text-red-700' : 'text-amber-800'}>
              {label && <span className="font-medium">{label}: </span>}
              {f.message}
            </div>
            {remedy && <div className="text-gray-600">{remedy}</div>}
          </div>
        );
      })}
    </div>
  );
};

// Human review sign-off + notes for the selected field (bd polyglot-pdf-u8t6).
// Distinct from the AUTOMATIC "Why this field is flagged" banner above: this is
// where an editor records THEIR judgment -- mark an auto-amber field
// "reviewed - correct" (turns it green), flag one "needs follow-up", and leave a
// note for themselves/others. Commits through the field-level _review helpers so
// a neutral reset serializes clean (no dangling {status:'unreviewed'}).
const REVIEW_CHOICES: { value: FieldReviewStatus; label: string }[] = [
  { value: 'unreviewed', label: 'Un-reviewed' },
  { value: 'reviewed_correct', label: 'Reviewed - correct' },
  { value: 'needs_followup', label: 'Needs follow-up' },
];

// The sentinel the review dropdown uses for Ignored (bd polyglot-pdf-mzkw). It
// is NOT a FieldReviewStatus: ignoring RELOCATES the field out of fields[], so
// it cannot ride withReviewStatus's single-field patch -- picking it routes to
// onIgnoreField instead, and the <select> reverts (the field is about to leave
// the pane entirely).
const IGNORE_OPTION = '__ignore__';

const FieldReviewEditor: React.FC<{
  field: FormField;
  onUpdateField: (field: FormField) => void;
  // Quarantine this field (bd mzkw). Returns a block reason to show, or null on
  // success. Absent -> the Ignored option is not offered at all.
  onIgnoreField?: (fieldId: string) => string | null;
  // Why ignoring is currently refused (required / has dependents), or null when
  // it is allowed. Drives the disabled option + its inline explanation.
  ignoreBlocked?: string | null;
  // The field's current lint findings (sprint-18 C1): marking reviewed_correct
  // is the SIGN-OFF, which stamps their fingerprints into
  // _review.seen_fingerprints -- the timeliness rule's baseline. Pass what is
  // in hand; undefined (no report) stamps the empty set, so later findings
  // honestly count as new.
  lintFindings?: LintFinding[];
}> = ({ field, onUpdateField, onIgnoreField, ignoreBlocked, lintFindings }) => {
  const review = getReview(field);
  const [ignoreError, setIgnoreError] = React.useState<string | null>(null);
  // The field is signed off, but a finding has appeared since -- so the
  // effective status is amber while the STORED status still reads
  // reviewed_correct (the demotion is a derivation, never a stored write).
  // Drives the re-confirm control below (Opus outer review, pass 9).
  //
  // NOT offered while a lint ERROR is anchored to the field (pass 10): red
  // wins over the timeliness clause in effectiveStatus AND in
  // isCountedReviewed, so re-stamping there would change nothing visible --
  // a success-shaped no-op that teaches the reviewer the control is
  // unreliable. An ERROR is fixed, never confirmed away.
  // Scoped ONCE and used for every read AND write below: the prop type
  // invites a whole-schema list, and this is the one WRITE path (the sign-off
  // stamps seen_fingerprints), so an unscoped list would persist another
  // field's fingerprints here -- permanently masking a genuine later finding
  // that happens to match one. The read paths in this file were hardened the
  // same way in earlier rounds; this closes the last seam (second confirming
  // review).
  const ownFindings = React.useMemo(
    () => (lintFindings ?? []).filter(f => f.field_id === field.id),
    [lintFindings, field.id],
  );
  const hasErrorFinding = ownFindings.some(f => f.severity === 'ERROR');
  const staleSignoff = !hasErrorFinding
    && newFindingsSinceReview(field, ownFindings);

  const handleStatusChange = (value: string) => {
    setIgnoreError(null);
    if (value === IGNORE_OPTION) {
      // Confirm first: ignoring is a deliberate, visible act (and reversible --
      // say so, so the dialog does not read like a delete).
      const label = field.spoken_name || field.id;
      const ok = window.confirm(
        `Ignore "${label}"?\n\n`
        + 'It will be set aside: hidden from the form, the checks and the '
        + 'progress count -- but NOT deleted. You can un-ignore it at any time '
        + 'from the Ignored list.',
      );
      if (!ok) return; // <select> reverts on re-render; nothing committed
      const reason = onIgnoreField?.(field.id) ?? null;
      if (reason) setIgnoreError(reason);
      return;
    }
    onUpdateField(
      withReviewStatus(field, value as FieldReviewStatus, ownFindings));
  };

  return (
    <div className="space-y-3 border-t border-gray-200 pt-4" data-testid="field-review">
      <h4 className="text-sm font-semibold text-gray-900">Review</h4>
      <div>
        <label className="label" htmlFor="review-status-select">Review status</label>
        <select
          id="review-status-select"
          className="input"
          aria-label="Review status"
          value={review.status}
          onChange={(e) => handleStatusChange(e.target.value)}
        >
          {REVIEW_CHOICES.map(({ value, label }) => (
            <option key={value} value={value}>{label}</option>
          ))}
          {onIgnoreField && (
            <option value={IGNORE_OPTION} disabled={!!ignoreBlocked}>
              Ignored -- not on this form
              {ignoreBlocked ? ' (unavailable)' : ''}
            </option>
          )}
        </select>
        <p className="text-xs text-gray-500 mt-1">
          "Reviewed - correct" marks a field done even if the tool still flags it
          amber -- unless its guidance changed and awaits the "still correct"
          confirmation under Instructions. A real error (red) always stays red
          until fixed.
        </p>
        {/* The EXIT from the timeliness demotion (Opus outer review, pass 9).
            A finding that appeared after the sign-off sends the field back to
            needs-review, but the stored status is still reviewed_correct --
            so the <select> above already reads "Reviewed - correct" and
            re-picking it fires no change event. Without this the field is
            permanently amber with no control that can clear it, which is the
            dead end the ack gate had one layer down. Re-signing off re-stamps
            seen_fingerprints with what is on screen NOW. */}
        {staleSignoff && (
          <div className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-2">
            <p className="text-xs text-amber-900">
              New problems have been found on this field since it was marked
              reviewed, so it is back in the "to review" count. Read them
              above, then confirm you have seen them.
            </p>
            <button
              type="button"
              className="btn-sm btn-primary mt-1"
              data-testid="reconfirm-review"
              onClick={() => onUpdateField(
                withReviewStatus(field, 'reviewed_correct', ownFindings))}
            >
              I have seen these -- still reviewed
            </button>
          </div>
        )}
        {onIgnoreField && ignoreBlocked && (
          <p className="text-xs text-gray-500 mt-1">{ignoreBlocked}</p>
        )}
        {ignoreError && (
          <p className="text-xs text-red-600 mt-1" role="alert">{ignoreError}</p>
        )}
      </div>
      <div>
        <label className="label" htmlFor="review-note">Review notes</label>
        <textarea
          id="review-note"
          className="input"
          rows={2}
          aria-label="Review notes"
          value={review.note || ''}
          onChange={(e) => onUpdateField(withReviewNote(field, e.target.value))}
          placeholder="Notes for yourself or other editors about this field..."
        />
      </div>
    </div>
  );
};

const FIELD_TYPES: FieldType[] = [
  'text',
  'textarea',
  'date',
  'number',
  'tel',
  'email',
  'select',
  'radio',
  'checkbox',
  'checkbox_group',
  'signature',
];

// "Add from PDF widgets" picker (bd polyglot-pdf-nivy, P5.3c). A self-contained
// sub-component (own hooks) so it can live inside the options section without
// tangling FieldEditor's early `if (!field)` return. Lists the kit's unclaimed
// PDF button widgets; selecting one appends an option (a slug minted from the
// widget's tooltip/leaf label, the widget name on option.pdf_field_name, and its
// on-state on option.pdf_on_value).
const WidgetPicker: React.FC<{
  // The field's EXISTING option VALUES (not labels): the new slug must be unique
  // against these, since option.value is what the lint duplicate-value rule keys
  // on. Minting against labels would miss a hand-edited value that collides
  // (fresh-eyes) -> an option-value-duplicate ERROR, breaking the lint-clean
  // exit criterion.
  existingValues: string[];
  onLoad: () => Promise<UnclaimedWidget[]>;
  // Append the picked widget as an option. For a SHARED-name group kid, the
  // caller must also set the field-level pdf_field_name (carried in
  // fieldPdfFieldName) and the option carries only pdf_on_value; for a distinct
  // widget the option carries pdf_field_name and fieldPdfFieldName is undefined.
  onPick: (opt: { label: string; value: string;
                  pdf_field_name?: string; pdf_on_value?: string },
           fieldPdfFieldName?: string) => void;
}> = ({ existingValues, onLoad, onPick }) => {
  const [open, setOpen] = React.useState(false);
  const [widgets, setWidgets] = React.useState<UnclaimedWidget[] | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const openPicker = React.useCallback(async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      setWidgets(await onLoad());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load PDF widgets');
    } finally {
      setLoading(false);
    }
  }, [onLoad]);

  // A readable default label from the tooltip, else the widget's leaf name.
  const labelFor = (w: UnclaimedWidget): string => {
    if (w.tooltip && w.tooltip.trim()) return w.tooltip.trim();
    const leaf = w.name.split('.').pop() || w.name;
    return leaf;
  };

  const pick = (w: UnclaimedWidget) => {
    const label = labelFor(w);
    // Mint the slug from the label, then bump it past every EXISTING option value
    // (option-value-duplicate keys on value, not label) so adding a widget can
    // never manufacture a duplicate -- even against a hand-edited value.
    const used = new Set(existingValues);
    const base = mintOptionSlug(label);
    let value = base;
    let n = 1;
    while (used.has(value)) value = `${base}_${++n}`;
    if (w.shared_name) {
      // Shared-name group kid: the option carries ONLY pdf_on_value; the field
      // carries pdf_field_name=name. Putting the shared name on each option's
      // pdf_field_name would trip dump-widget-multiclaim (Opus fallback).
      onPick(
        { label, value, ...(w.on_value ? { pdf_on_value: w.on_value } : {}) },
        w.name,
      );
    } else {
      // Distinct-name widget: the option carries its own pdf_field_name.
      onPick({
        label, value, pdf_field_name: w.name,
        ...(w.on_value ? { pdf_on_value: w.on_value } : {}),
      });
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        className="btn btn-secondary w-full text-sm"
        onClick={() => void openPicker()}
      >
        + Add from PDF widgets
      </button>
    );
  }

  return (
    <div className="border border-gray-200 rounded-md p-2 space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-700">
          Unclaimed PDF widgets
        </span>
        <button
          type="button"
          className="text-xs text-gray-500 hover:text-gray-700"
          onClick={() => setOpen(false)}
        >
          Close
        </button>
      </div>
      {loading && <p className="text-xs text-gray-500">Loading...</p>}
      {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
      {!loading && !error && widgets && widgets.length === 0 && (
        <p className="text-xs text-gray-500">
          No unclaimed PDF widgets -- every button is already mapped.
        </p>
      )}
      {!loading && widgets && widgets.map((w) => (
        <button
          // A shared-name group returns N candidates with the SAME name (differing
          // only by on_value), so key on name+on_value to avoid duplicate React
          // keys (Opus fallback).
          key={`${w.name}|${w.on_value ?? ''}`}
          type="button"
          className="w-full text-left text-xs p-1.5 rounded hover:bg-gray-100 flex items-center justify-between gap-2"
          onClick={() => pick(w)}
          title={`Add ${w.name} as an option`}
        >
          <span className="truncate">{labelFor(w)}</span>
          <span className="font-mono text-gray-400 shrink-0">
            {w.type}{w.page != null ? ` p${w.page + 1}` : ''}
          </span>
        </button>
      ))}
    </div>
  );
};

// The per-option backing-widget selector (bd polyglot-pdf-mrdj). Replaces a
// free-text pdf_field_name box: a typo or invented name silently broke that
// option's round-trip fill (the fill route writes widgets BY pdf_field_name,
// so an unknown name just never fills). The editor may REASSIGN an option to a
// different REAL widget but can never invent a name.
//
// Choices are the union of (a) every pdf_field_name already referenced by this
// field's options -- so the current value is always selectable and the author
// can reassign within the group -- and (b) the kit's unclaimed button widgets
// (hosted author mode only, loaded lazily on first open). Local mode with no
// backend dump still gets (a): reassignment among the group's existing widgets,
// never free text.
const OptionWidgetSelect: React.FC<{
  value: string;                  // this option's current pdf_field_name ('' if none)
  siblingNames: string[];         // pdf_field_names claimed by OTHER options (excluded)
  onLoadUnclaimedWidgets?: () => Promise<UnclaimedWidget[]>;
  onChange: (name: string) => void;
  ariaLabel: string;
}> = ({ value, siblingNames, onLoadUnclaimedWidgets, onChange, ariaLabel }) => {
  const [unclaimed, setUnclaimed] = React.useState<string[] | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadUnclaimed = React.useCallback(async () => {
    if (!onLoadUnclaimedWidgets || unclaimed !== null || loading) return;
    setLoading(true);
    setError(null);
    try {
      const ws = await onLoadUnclaimedWidgets();
      // EXCLUDE shared-name widgets: a shared-AcroForm-name radio group has N
      // same-named kids disambiguated only by on_value, so assigning its bare
      // name to a single option's pdf_field_name would fill the WRONG kid
      // deterministically (the fill route's find_widget(name) returns the
      // first match, no on-state disambiguation). Such widgets belong to a
      // group via the field-level pdf_field_name + option pdf_on_value, never
      // a per-option pdf_field_name (bd mrdj fresh-eyes round 2).
      setUnclaimed(Array.from(new Set(
        ws.filter(w => !w.shared_name).map(w => w.name))));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load PDF widgets');
    } finally {
      setLoading(false);
    }
  }, [onLoadUnclaimedWidgets, unclaimed, loading]);

  // The selectable set: this option's CURRENT value + the loaded unclaimed
  // widgets, MINUS any name already claimed by a sibling option (assigning a
  // sibling's widget to this option makes two options claim one widget -- a
  // silent duplicate that fills WRONG, with the last-processed option
  // overwriting the other's value; the local checkFieldComplete never flags
  // it and the multiclaim lint is dump-gated so it may not run either; bd
  // mrdj outer review). De-duped, current-first so it always shows mid-load.
  const choices = React.useMemo(() => {
    const claimed = new Set(siblingNames);
    const seen = new Set<string>();
    const out: string[] = [];
    // the current value is always offered even if (pathologically) a sibling
    // also claims it -- so the author can SEE and change it, not be stuck.
    for (const n of [value, ...(unclaimed ?? [])]) {
      if (n && n !== value && claimed.has(n)) continue;
      if (n && !seen.has(n)) { seen.add(n); out.push(n); }
    }
    return out;
  }, [value, siblingNames, unclaimed]);

  return (
    <div className="mt-1">
      <select
        className="input input-sm w-full font-mono"
        value={value}
        aria-label={ariaLabel}
        onFocus={() => void loadUnclaimed()}
        onChange={(e) => onChange(e.target.value)}
      >
        {/* An empty current value stays selectable but is not a real widget. */}
        {!value && <option value="">(no widget assigned)</option>}
        {choices.map(name => (
          <option key={name} value={name}>{name}</option>
        ))}
      </select>
      {loading && <p className="text-xs text-gray-400 mt-0.5">Loading widgets...</p>}
      {error && <p className="text-xs text-red-600 mt-0.5" role="alert">{error}</p>}
    </div>
  );
};

/**
 * "Rewrite it from the instructions booklet" -- the costly half of the
 * guidance staleness gate (bd polyglot-pdf-cpiw).
 *
 * Its own component because FieldEditor returns early when no field is
 * selected, so it cannot hold hooks; the in-flight and error state lives here
 * instead. Keyed by field id at the call site so switching fields resets it.
 */
const RegenerateGuidanceButton: React.FC<{
  fieldId: string;
  onRegenerate: (fieldId: string) => Promise<boolean>;
}> = ({ fieldId, onRegenerate }) => {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // A rewrite that CHANGED NOTHING resolves normally, so without this the
  // button just returns to its idle label and the amber banner is still there
  // with no explanation -- the same silent, success-shaped no-op this whole
  // change exists to remove. Three real ways to get here: the judge was
  // unavailable, the guidance was hand-edited (which the route deliberately
  // never clobbers), or the booklet yielded nothing for this field.
  const [noChange, setNoChange] = React.useState(false);
  return (
    <div className="mt-2 border-t border-amber-200 pt-2">
      <button
        type="button"
        className="text-xs font-medium text-amber-900 underline disabled:no-underline disabled:opacity-60"
        data-testid="regenerate-guidance"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          setNoChange(false);
          try {
            const changed = await onRegenerate(fieldId);
            setNoChange(!changed);
          } catch (err) {
            setError(err instanceof Error
              ? err.message
              : 'Could not regenerate the guidance');
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy
          ? 'Rewriting from the instructions booklet...'
          : 'Or rewrite it from the instructions booklet'}
      </button>
      {error && (
        <p className="mt-1 text-xs text-red-700" role="status">{error}</p>
      )}
      {noChange && !error && (
        <p className="mt-1 text-xs text-amber-900" role="status">
          Nothing was rewritten. The guidance may have been edited by hand
          (which is never overwritten), or the booklet had nothing to say about
          this field -- confirm the existing text instead.
        </p>
      )}
    </div>
  );
};

export const FieldEditor: React.FC<FieldEditorProps> = ({
  field,
  schema,
  onUpdateField,
  onRenameField,
  onUnmergeField,
  onChangeGroupKind,
  onUpdateMetadata,
  onUpdateFields,
  authorTier = true,
  onLoadUnclaimedWidgets,
  lintFindings,
  pageCount,
  onIgnoreField,
  ignoreBlocked,
  onRegenerateGuidance,
}) => {
  // For the header chip's scroll-to-first-finding (sprint-18 C1). Declared
  // unconditionally, before the no-field early return, per the rules of hooks.
  const rootRef = React.useRef<HTMLDivElement | null>(null);

  if (!field) {
    // No field selected -> show the editable form-metadata panel (bd s4dp.2), so
    // version/edition/OMB/expiration are reachable without picking a field.
    return <FormMetadataEditor schema={schema} onUpdateMetadata={onUpdateMetadata} />;
  }

  const updateField = (updates: Partial<FormField>) => {
    onUpdateField({ ...field, ...updates });
  };

  // Bucket this field's findings by the PROPERTY they concern (sprint-18 C1,
  // decision 1): the finding paths already name it, so each renders under the
  // control it is about instead of in a detached list. The staleness finding
  // (GUIDANCE_STALE_RULE) is excluded here -- its rendering IS the dedicated
  // amber ack-gate box under Instructions, which also owns its acked-state
  // suppression (bd hii0).
  const anchored: {
    instructions: LintFinding[];
    details: LintFinding[];
    conditions: LintFinding[];
    field: LintFinding[];
    byOption: Map<number, LintFinding[]>;
  } = {
    instructions: [], details: [], conditions: [], field: [],
    byOption: new Map(),
  };
  // Visibility coherence (bd polyglot-pdf-pfx1). A field may not be BOTH
  // always-hidden and conditionally shown; this drives the mutual gate on the
  // Hidden checkbox and the "Shown when" card.
  const hasShowIf = hasCondition(field.show_if);

  // The maintainer's "how will editors be reminded which hidden is active?"
  // question: the effective behavior, readable without cross-referencing the
  // Hidden checkbox against a condition card elsewhere in the panel. Not
  // cross-referencing is exactly how the ambiguity went unnoticed.
  const effectiveVisibility = field.hidden
    ? (hasShowIf ? 'Conflict: hidden AND conditional' : 'Always hidden')
    : (hasShowIf ? 'Shown when a condition matches' : 'Always shown');

  // safeOptionsPreservingArity (bd polyglot-pdf-8bjdx): a non-array or
  // null-bearing `options` threw out of this .map. Arity preserved because
  // the values are matched positionally against the option rows below.
  const optionValues = safeOptionsPreservingArity(field).map(o =>
    o?.value !== undefined ? String(o.value) : undefined);
  // The Options block below renders only for these types -- an option bucket
  // on any OTHER options-carrying field (backend lint checks options[] on
  // every field regardless of type) would be counted by the chip yet render
  // nowhere, the same homeless class the Form-row fix closed (fresh-eyes
  // round 3). Those findings fall to the banner instead.
  const optionsBlockRenders = field.type === 'select'
    || field.type === 'radio' || field.type === 'checkbox_group';
  for (const f of lintFindings ?? []) {
    // Scope to THIS field: the sole caller passes a pre-scoped array, but the
    // prop type invites a whole-schema list, and anchoring another field's
    // finding at this field's controls would mis-locate the problem (same
    // hazard the gate lookup below guards against -- fresh-eyes, closeout
    // round 1).
    if (f.field_id !== field.id) continue;
    if (f.rule === GUIDANCE_STALE_RULE) continue;
    const a = propertyAnchor(f);
    if (a.kind === 'options') {
      // The token may be an option INDEX (schema_lint's option rules) or an
      // option VALUE (the translation-flag writers) -- resolveOptionIndex
      // disambiguates per rule. An unresolvable token (option gone mid-edit,
      // ambiguous value) -- or a field whose Options block never renders --
      // falls back to the field bucket rather than rendering nowhere or at a
      // wrong row.
      const idx = optionsBlockRenders && a.optionToken !== undefined
        ? resolveOptionIndex(optionValues, f, a.optionToken)
        : undefined;
      if (idx !== undefined) {
        const bucket = anchored.byOption.get(idx);
        if (bucket) bucket.push(f);
        else anchored.byOption.set(idx, [f]);
      } else {
        anchored.field.push(f);
      }
    } else if (a.kind === 'field') {
      anchored.field.push(f);
    } else {
      anchored[a.kind].push(f);
    }
  }
  const embeddedCount =
    anchored.instructions.length + anchored.details.length
    + anchored.conditions.length
    + [...anchored.byOption.values()].reduce((n, b) => n + b.length, 0);
  // Scoped to THIS field like the bucketing loop above -- an unscoped count
  // let another field's ERROR turn this field's chip red ("N to fix") when a
  // caller passes a multi-field list (fresh-eyes round 1).
  const anchoredErrorTotal = (lintFindings ?? [])
    .filter(f => f.field_id === field.id
      && f.rule !== GUIDANCE_STALE_RULE && f.severity === 'ERROR').length;
  const anchoredTotal = embeddedCount + anchored.field.length;

  return (
    <div className="h-full overflow-auto custom-scrollbar" ref={rootRef}>
      <div className="p-4 space-y-6">
        {/* Header. key={field.id} remounts the id editor on rename/selection
            change so its draft state never leaks across fields. */}
        <div className="border-b border-gray-200 pb-4">
          <div className="flex items-center justify-between gap-2">
            {onRenameField ? (
              <FieldIdHeader key={field.id} fieldId={field.id} onRenameField={onRenameField} />
            ) : (
              <h3 className="text-lg font-semibold text-gray-900">{field.id}</h3>
            )}
            {/* The field's finding count as a CONTROL (sprint-18 C1): click
                scrolls to the first finding, which renders at the property it
                concerns. */}
            {anchoredTotal > 0 && (
              <button
                type="button"
                data-testid="field-findings-chip"
                className={`shrink-0 text-[11px] font-semibold rounded-full px-2 py-0.5 border ${
                  anchoredErrorTotal > 0
                    ? 'bg-red-100 text-red-700 border-red-200'
                    : 'bg-amber-100 text-amber-800 border-amber-200'
                }`}
                title="Jump to the first finding on this field"
                onClick={() => {
                  // Prefer a property-anchored finding; the advisory banner is
                  // only the fallback. A combined selector resolved in DOCUMENT
                  // order, and the banner (rendered above every anchor, often
                  // for advisory reasons the chip did not count) swallowed the
                  // scroll whenever it existed (fresh-eyes round 3).
                  const target =
                    rootRef.current?.querySelector('[data-embedded-finding]')
                    ?? rootRef.current?.querySelector('[data-testid="field-problems"]');
                  target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }}
              >
                {anchoredErrorTotal > 0
                  ? `${anchoredTotal} to fix`
                  : `${anchoredTotal} notice${anchoredTotal !== 1 ? 's' : ''}`}
              </button>
            )}
          </div>
          <p className="text-sm text-gray-500 font-mono">{field.pdf_field_name}</p>
        </div>

        {/* Why this field is flagged (bd polyglot-pdf-0x10.6): the list's red X /
            amber clock, explained AT the field. Since sprint-18 C1 this banner
            carries only what has no property home -- the local completeness
            errors/reasons (the advisory WHY-list) and the FIELD-anchored lint
            findings (no backing widget, review-state rules). A finding about a
            specific property (Instructions, an option row, a condition)
            renders UNDER that control instead, where the fix happens.
            Severity-aware styling (bd polyglot-pdf-6hhc): ERROR-class findings
            (and local completeness errors, which ARE errors) render red to
            match FieldList.getFieldStatus's red row; WARNING-class findings
            render amber. */}
        {(() => {
          const completeness = checkFieldComplete(field, pageCount);
          const errors = [
            ...completeness.errors,
            ...anchored.field
              .filter(f => f.severity === 'ERROR')
              .map(f => f.message),
          ];
          const warnings = [
            // The automatic amber reasons (bd polyglot-pdf-g63j): a field
            // flagged amber in the list -- e.g. a named widget with no
            // drawable position -- is explained in the pane the author is
            // actually editing in.
            ...completeness.reviewReasons,
            ...anchored.field
              .filter(f => f.severity !== 'ERROR')
              .map(f => f.message),
          ];
          if (errors.length === 0 && warnings.length === 0) return null;
          const hasErrors = errors.length > 0;
          return (
            <div
              className={
                hasErrors
                  ? 'bg-red-50 border border-red-200 rounded-md p-3 space-y-1'
                  : 'bg-amber-50 border border-amber-200 rounded-md p-3 space-y-1'
              }
              role="alert"
              data-testid="field-problems"
            >
              <p className={`text-xs font-semibold ${
                hasErrors ? 'text-red-700' : 'text-amber-700'}`}>
                Why this field is flagged
              </p>
              <ul className="list-disc list-inside space-y-0.5">
                {errors.map((message, i) => (
                  <li key={`e${i}`} className="text-xs text-red-700">{message}</li>
                ))}
                {warnings.map((message, i) => (
                  <li key={`w${i}`} className="text-xs text-amber-700">{message}</li>
                ))}
              </ul>
            </div>
          );
        })()}

        {/* Human review sign-off + notes (bd polyglot-pdf-u8t6).
            key={field.id} remounts it on selection change, exactly as the id
            header above does: it holds a local ignoreError, and without the
            remount a block reason earned by THIS field would still be on
            screen under the NEXT one, blaming a field that may have no
            dependents at all (bd mzkw, fresh-eyes). */}
        <FieldReviewEditor
          key={field.id}
          field={field}
          onUpdateField={onUpdateField}
          onIgnoreField={onIgnoreField}
          ignoreBlocked={ignoreBlocked}
          lintFindings={lintFindings}
        />

        {/* Basic Properties */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">Basic Properties</h4>

          {/* Field Type. A field that already carries options[] is a GROUP
              (checkbox_group / a consolidated radio); raw-switching its type to
              a NON-group type (text, date, ...) would strand the options, so the
              base picker stays read-only for groups. But flipping BETWEEN the two
              group kinds (checkbox_group <-> radio) is safe -- they share the same
              options[] and per-option PDF mapping, differing only in single- vs
              multi-select -- so a group gets a dedicated "Group behaves as"
              selector below (bd polyglot-pdf-checkbox-radio) instead of the old
              dead-end "reversed by Ungroup" hint. checkbox_group is only OFFERED
              as a target to authors, since building a valid one requires
              per-option PDF mapping (Codex PR #310 round 2). */}
          {(() => {
            const isGroup = !!field.options && field.options.length > 0;
            const typeChoices = FIELD_TYPES.filter(
              t => t !== 'checkbox_group' || authorTier || field.type === 'checkbox_group',
            );
            // The in-place kind flip is offered only for a group that is
            // currently one of the two kinds and only when the caller wired the
            // handler (author-tier: minting a checkbox_group needs author
            // surfaces, matching the type picker's checkbox_group gate).
            const canFlipKind =
              isGroup &&
              !!onChangeGroupKind &&
              authorTier &&
              (field.type === 'checkbox_group' || field.type === 'radio');
            return (
              <div>
                <label className="label">Field Type</label>
                <select
                  className="input disabled:opacity-60"
                  aria-label="Field Type"
                  value={field.type}
                  disabled={isGroup}
                  title={isGroup
                    ? 'This is a group (has options). Switch single- vs multi-select below; use Ungroup to split it into separate fields.'
                    : undefined}
                  onChange={(e) => updateField({ type: e.target.value as FieldType })}
                >
                  {typeChoices.map(type => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
                {isGroup && !canFlipKind && (
                  <p className="text-xs text-gray-500 mt-1">
                    Group type is set by Merge (several = checkbox group, exactly
                    one = radio) and reversed by Ungroup.
                  </p>
                )}
                {canFlipKind && (() => {
                  // The two kinds are NOT symmetric, so flipping TO
                  // checkbox_group can be refused for two DIFFERENT reasons, each
                  // needing its own fix (bd polyglot-pdf-8qfj, fresh-eyes):
                  //   'pdf-widgets' -- a shared-name radio (one PDF widget across
                  //     its options) has no valid checkbox_group form; re-plumb
                  //     widgets. 'nested-list-membership' -- a dependent has an
                  //     in/not_in condition nested in a composite that can't be
                  //     rewritten for a multi-select trigger; retarget it. Naming
                  //     the wrong cause sends the author to fix the wrong thing.
                  // Flipping TO radio is always valid. A field ALREADY of the
                  // target kind is trivially "allowed" (same-kind), so treat only
                  // a genuine block reason as a disable.
                  const cbBlock = field.type === 'checkbox_group'
                    ? null
                    : changeGroupKindBlockReason(schema, field, 'checkbox_group');
                  const canBecomeCheckboxGroup = cbBlock === null;
                  const cbBlockHint = cbBlock === 'nested-list-membership'
                    ? 'A field shown/required by an "is one of" (in / not-in) condition '
                      + 'on this group blocks the switch to multi-select. Retarget that '
                      + 'condition first, then switch.'
                    : 'This group shares one PDF widget across its options, so it '
                      + 'can only be a radio (choose one). A checkbox group needs a '
                      + 'separate PDF widget per option.';
                  return (
                    <div className="mt-2">
                      <label className="label" htmlFor="group-kind-select">
                        Group behaves as
                      </label>
                      <select
                        id="group-kind-select"
                        className="input"
                        aria-label="Group behaves as"
                        value={field.type}
                        onChange={(e) =>
                          onChangeGroupKind!(
                            field.id,
                            e.target.value as 'checkbox_group' | 'radio',
                          )
                        }
                      >
                        <option value="radio">Radio (choose exactly one)</option>
                        <option
                          value="checkbox_group"
                          disabled={!canBecomeCheckboxGroup}
                        >
                          Checkbox group (choose several)
                          {!canBecomeCheckboxGroup ? ' -- unavailable' : ''}
                        </option>
                      </select>
                      <p className="text-xs text-gray-500 mt-1">
                        Both kinds share the same options and PDF mapping; only
                        single- vs multi-select changes. To split the group back
                        into separate fields, use Ungroup.
                      </p>
                      {!canBecomeCheckboxGroup && (
                        <p className="text-xs text-gray-500 mt-1">{cbBlockHint}</p>
                      )}
                    </div>
                  );
                })()}
              </div>
            );
          })()}

          {/* Spoken Name */}
          <div>
            <label className="label">Spoken Name</label>
            <input
              type="text"
              className="input"
              value={field.spoken_name || ''}
              onChange={(e) => {
                // A spoken-name edit invalidates the field's baked
                // spoken_name_translations -- they translate the OLD text, so
                // a renamed field would be SPOKEN in the old wording in every
                // non-English session (bd polyglot-pdf-tupu.3; same rule as
                // the option label_translations drop, bd d25e). Drop the key
                // entirely on the first real change; the editor's
                // Translate-options action or translate_option_labels.py
                // re-bakes on demand.
                const edited = { ...field, spoken_name: e.target.value };
                delete edited.spoken_name_translations;
                onUpdateField(edited);
              }}
              placeholder="e.g., alien registration number"
            />
            <p className="text-xs text-gray-500 mt-1">
              User-friendly name for voice AI
            </p>
          </div>

          {/* Section */}
          <div>
            <label className="label">Section</label>
            <select
              className="input"
              aria-label="Section"
              value={field.section_id || ''}
              onChange={(e) => {
                // Reassigning a field's section must move it between the
                // section.fields[] arrays too, not just patch field.section_id
                // -- FieldList renders from section.fields[] and the section
                // remove/merge ops trust it, so a section_id-only patch drifts
                // the two apart (bd polyglot-pdf-w7rg). Commit the whole
                // {fields, sections} atomically via onUpdateFields when it is
                // available; fall back to the single-field patch otherwise.
                const dest = e.target.value || null;
                if (onUpdateFields) {
                  const moved = moveFieldToSection(
                    schema.fields, schema.sections, schema.parts,
                    field.id, dest,
                  );
                  onUpdateFields(moved.fields, moved.sections);
                } else {
                  updateField({ section_id: dest ?? undefined });
                }
              }}
            >
              <option value="">No section</option>
              {schema.sections.map(section => (
                <option key={section.id} value={section.id}>
                  {section.label}
                </option>
              ))}
            </select>
          </div>

          {/* Checkboxes */}
          <div className="space-y-2">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={!!field.validation?.required}
                onChange={(e) => updateField({
                  validation: { ...field.validation, required: e.target.checked },
                })}
                className="rounded"
              />
              <span className="text-sm text-gray-700">Required</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={field.read_only}
                onChange={(e) => updateField({ read_only: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-gray-700">Read Only</span>
            </label>
            {/* NO BYPASS, for two independent reasons -- both re-verified,
                because the first version of this comment got the second one
                WRONG (outer review: it claimed fieldGrouping only writes
                section-level show_if; there are six FIELD-level writes):
                  1. This checkbox is the ONLY writer of `hidden` anywhere in
                     schema-editor/src, so nothing else can set that half.
                  2. Every field-level `show_if` write in fieldGrouping is
                     precondition-guarded on the field ALREADY having a
                     condition (`if (f.show_if && ...)` at the retarget, merge,
                     kind-flip, restore and fallback-remap sites), so they
                     REWRITE and never CREATE. The one unguarded write
                     (mergeFields' `mergedField.show_if = primaryShowIf`) takes
                     `hidden` and the condition from the SAME source field, so
                     it cannot combine them from two.
                A new write that creates a condition from nothing would break
                reason 2 -- add it to the gate if you add one. */}
            {/* GATE, not a warning (bd polyglot-pdf-pfx1, maintainer decision
                2026-08-04): a field may not be BOTH always-hidden and
                conditionally shown. A warning would still let the state reach a
                saved kit, leaving every consumer to interpret it -- bd
                polyglot-pdf-ubam had to fix SIX sites that each interpreted it
                differently. Disabling the control makes it unauthorable.
                Today the CONDITION silently wins in shouldShowField, so the
                contradiction resolves in the RISKIER direction: a field marked
                never-show APPEARS to the applicant when its condition matches. */}
            <label
              className={`flex items-center gap-2 ${hasShowIf ? 'opacity-50' : ''}`}
              title={hasShowIf
                ? 'Unavailable: this field has a "show when" condition. A field '
                  + 'cannot be both always-hidden and conditionally shown. Delete '
                  + 'the condition to make it always-hidden.'
                : undefined}
            >
              <input
                type="checkbox"
                checked={field.hidden || false}
                disabled={hasShowIf}
                onChange={(e) => updateField({ hidden: e.target.checked })}
                className="rounded"
              />
              <span className="text-sm text-gray-700">Hidden</span>
            </label>
          </div>
          {hasShowIf && (
            <p className="text-xs text-gray-500">
              Hidden is unavailable while this field has a "show when"
              condition -- it is shown only when the condition matches. Delete
              the condition to make it always hidden.
            </p>
          )}
          {/* EFFECTIVE VISIBILITY (bd polyglot-pdf-pfx1). One computed label so
              the real behavior is readable here, instead of inferred by
              cross-referencing this checkbox against a condition card further
              down the panel -- the cross-reference nobody made, which is how
              the hidden/show_if ambiguity went unnoticed. */}
          <p className="text-xs">
            <span className="text-gray-500">Effective visibility: </span>
            <span
              className={field.hidden && hasShowIf
                ? 'font-semibold text-red-600'
                : 'font-medium text-gray-700'}
            >
              {effectiveVisibility}
            </span>
          </p>
        </div>

        {/* Help Text */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">Help & Guidance</h4>

          {(() => {
            // Guidance staleness gate (bd polyglot-pdf-anim). The BACKEND owns
            // the comparison (it wrote the hash, so it compares it -- no
            // cross-language hash contract to drift); the editor consumes the
            // finding and turns it into a human acknowledgment. A trivial
            // rename must not cost an LLM call, so confirming is one free
            // click; re-authoring stays a deliberate, separate action.
            const staleFinding = (lintFindings ?? []).find(
              // Scope by field id like currentIdentity below: the sole caller
              // passes a pre-scoped array today, but this component's prop type
              // invites a whole-schema list, and an unscoped match would amber
              // EVERY field once ANY field drifts (fresh-eyes, closeout round 1).
              f => f.rule === GUIDANCE_STALE_RULE && f.field_id === field.id);
            // Pin the DISPLAY to the current identity, exactly as the write
            // path and the row gate do. A naive "some ack exists" check
            // rendered the box already-ticked after a SECOND drift -- showing
            // content as reviewed that the human has never seen, which is the
            // permanent-waiver hole surviving in the one surface a reviewer
            // actually reads (bd anim fresh-eyes round 3).
            const identity = currentIdentity(lintFindings, field.id);
            const acked = isAcknowledged(field, identity);
            // No parseable identity in the finding path -> fail OPEN like
            // needsGuidanceAck: rendering the gate would offer a checkbox
            // that can record nothing (withGuidanceAck without an identity
            // is a no-op) -- a dead control on a permanently amber field
            // (Opus round). Unreachable from today's contract-pinned backend.
            const gated = !!staleFinding && identity !== undefined;
            const stale = gated && !acked;
            return (
              <div>
                <label className="label">Instructions</label>
                <textarea
                  className={stale
                    ? 'input ring-2 ring-amber-400 border-amber-400'
                    : 'input'}
                  rows={3}
                  value={field.help?.instructions || ''}
                  onChange={(e) =>
                    updateField({
                      help: { ...field.help, instructions: e.target.value },
                    })
                  }
                  placeholder="Instructions for filling out this field..."
                />
                {/* Findings ABOUT the instructions render here, at the box
                    they concern (sprint-18 C1) -- too long, label
                    restatement, screen references, missing guidance. */}
                <EmbeddedFindings
                  findings={anchored.instructions}
                  anchor="instructions"
                />
                {gated && (
                  <div className="mt-1 rounded-md border border-amber-300 bg-amber-50 p-2">
                    <p className="text-xs text-amber-900">
                      {/* Names every hashed input, including the answer type
                          (bd polyglot-pdf-stkz). This is the sentence a
                          reviewer reads immediately before ticking the box, so
                          it is the copy that most has to be true: after a
                          text -> date edit, a message naming only the other
                          three sends them to check attributes that did not
                          change, and a gate that looks broken gets clicked
                          through. Kept in step with the backend lint message
                          (schema_lint._check_guidance_identity_drift). */}
                      This field's name, spoken name, options or answer type
                      changed after this guidance was written, so it may no
                      longer match what the assistant says.
                    </p>
                    <label className="mt-1 flex items-start gap-2 text-xs text-amber-900 cursor-pointer">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        data-testid="guidance-ack-checkbox"
                        checked={acked}
                        onChange={(e) =>
                          onUpdateField(withGuidanceAck(
                            field, identity, e.target.checked))
                        }
                      />
                      <span>
                        I have read these instructions and they are still
                        correct.
                        {!acked && (
                          <strong> Required before this field can be marked
                          reviewed.</strong>
                        )}
                      </span>
                    </label>
                    {/* The OTHER way out of the gate (bd polyglot-pdf-cpiw):
                        re-author from the booklet instead of confirming the
                        old text. Offered right here so a reviewer never has
                        to hand-copy prose out of the instructions PDF. */}
                    {onRegenerateGuidance && (
                      <RegenerateGuidanceButton
                        fieldId={field.id}
                        onRegenerate={onRegenerateGuidance}
                      />
                    )}
                  </div>
                )}
              </div>
            );
          })()}

          <div>
            <label className="label">Details (official reference text)</label>
            <textarea
              className="input font-mono text-xs"
              rows={6}
              value={field.help?.details || ''}
              onChange={(e) =>
                updateField({
                  help: { ...field.help, details: e.target.value },
                })
              }
              placeholder="Verbatim excerpts from the official instructions booklet for this field (AI reference only -- never shown to users)..."
            />
            {/* Findings ABOUT the details render at their box (sprint-18 C1):
                not a verbatim quote, oversize, missing headings... */}
            <EmbeddedFindings findings={anchored.details} anchor="details" />
          </div>

          <div>
            <label className="label">Format Hint</label>
            <input
              type="text"
              className="input"
              value={field.help?.format_hint || ''}
              onChange={(e) =>
                updateField({
                  help: { ...field.help, format_hint: e.target.value },
                })
              }
              placeholder="e.g., 7-9 digits, MM/DD/YYYY"
            />
          </div>
        </div>

        {/* Validation */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">Validation</h4>

          <div>
            <label className="label">Format Preset</label>
            <input
              type="text"
              className="input"
              value={field.validation?.format_preset || ''}
              onChange={(e) =>
                updateField({
                  validation: { ...field.validation, format_preset: e.target.value },
                })
              }
              placeholder="e.g., a_number, ssn, email"
            />
          </div>

          <div>
            <label className="label">Pattern (Regex)</label>
            <input
              type="text"
              className="input font-mono text-sm"
              value={field.validation?.pattern || ''}
              onChange={(e) =>
                updateField({
                  validation: { ...field.validation, pattern: e.target.value },
                })
              }
              placeholder="e.g., ^\d{7,9}$"
            />
          </div>

          {field.type === 'text' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Min Length</label>
                <input
                  type="number"
                  className="input"
                  value={field.validation?.min_length || ''}
                  onChange={(e) =>
                    updateField({
                      validation: {
                        ...field.validation,
                        min_length: e.target.value ? parseInt(e.target.value) : undefined,
                      },
                    })
                  }
                />
              </div>
              <div>
                <label className="label">Max Length</label>
                <input
                  type="number"
                  className="input"
                  value={field.max_length || field.validation?.max_length || ''}
                  onChange={(e) => {
                    const val = e.target.value ? parseInt(e.target.value) : undefined;
                    updateField({
                      max_length: val,
                      validation: { ...field.validation, max_length: val },
                    });
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Conditional Logic (bd h76m.9): composite builder cards for
            show_if ("Shown when") and require_if ("Required when"). */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-900">
            Conditional Logic
          </h4>

          {/* The other half of the pfx1 gate. The Hidden checkbox is disabled
              while a condition exists; here the reverse -- an always-hidden
              field cannot GAIN one. Rendering the explanation instead of the
              builder keeps the two states mutually exclusive by construction
              rather than by the author remembering. An existing condition is
              still shown (never silently dropped) -- but a field cannot be in
              that state via the editor, so this only renders for a schema that
              arrived by another route, where lint already reports
              hidden-with-show-if. */}
          {field.hidden && !field.show_if ? (
            <div className="panel p-3 bg-gray-50 border-dashed">
              <h5 className="text-sm font-medium text-gray-700">Shown when</h5>
              <p className="text-xs text-gray-500 mt-1">
                Unavailable: this field is marked <strong>Hidden</strong>, so it
                is never shown. Untick Hidden to show it only when a condition
                matches.
              </p>
            </div>
          ) : (
            <ConditionBuilder
              title="Shown when"
              condition={field.show_if}
              selfId={field.id}
              schema={schema}
              onChange={(next) => updateField({ show_if: next })}
            />
          )}

          <ConditionBuilder
            title="Required when"
            condition={field.require_if}
            selfId={field.id}
            schema={schema}
            onChange={(next) => updateField({ require_if: next })}
          />

          {/* Findings ABOUT this field's conditions render at the builders
              they concern (sprint-18 C1): unknown operator, unresolved
              reference, malformed shape... */}
          <EmbeddedFindings findings={anchored.conditions} anchor="conditions" />
        </div>

        {/* Un-group: split a consolidated options[] field back into one field
            per widget (bd polyglot-pdf-s4dp.1). Rendered for ANY consolidated
            field whose options each carry a pdf_field_name -- including CHECKBOX
            groups (e.g. I-90 p3_race), not just select/radio, so the control is
            not half-wired (Codex PR #256). */}
        {onUnmergeField && canUngroup(field) && (
          <div className="flex items-center justify-between border-t border-gray-200 pt-4">
            <span className="text-sm font-semibold text-gray-900">Consolidated group</span>
            <button
              className="btn-sm btn-secondary"
              onClick={() => onUnmergeField(field.id)}
              title="Split this consolidated field back into separate per-widget fields"
            >
              Ungroup
            </button>
          </div>
        )}

        {/* Field Options (select / radio / checkbox_group). The option VALUE
            is an internal join key minted from the label, never free-typed
            (bd h76m.10); editing the label is how an author renames an option,
            and the value re-mints once when the edit settles (blur). The value
            is shown only inside the author-tier Advanced disclosure, alongside
            the per-option PDF-widget mapping. */}
        {(field.type === 'select' || field.type === 'radio' || field.type === 'checkbox_group') && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-gray-900">Options</h4>
            </div>

            {/* ARITY-PRESERVING, and malformed rows are SKIPPED rather than
                compacted away (bd polyglot-pdf-8bjdx, fresh-eyes round 1).
                `idx` here is not just a React key -- it indexes
                anchored.byOption (built from optionValues above, which uses
                safeOptionsPreservingArity) and it is the index every edit
                handler below splices on. Rendering over the DROPPING variant
                gave this block a second, compacted index space: with
                options=[null, a, b], a finding anchored to raw index 1 (that
                is, option 'a') was looked up at 'b's row, and an edit to 'a'
                spliced position 0. One index space, raw, is the invariant --
                a malformed entry renders nothing but still consumes its slot.
                The write handlers deliberately keep safeOptions(): they
                REBUILD options, and dropping the malformed entry there is the
                repair, not a desync. */}
            {safeOptions(field).length > 0 ? (
              <div className="space-y-2">
                {safeOptionsPreservingArity(field).map((option, idx) => (
                  option === null ? null : (
                  <div key={idx} className="space-y-1 border-l-2 border-gray-100 pl-2">
                    {/* Findings ABOUT this option render at its row
                        (sprint-18 C1): missing/duplicate/comma value, wrong
                        slug format, translation flags... */}
                    <EmbeddedFindings
                      findings={anchored.byOption.get(idx) ?? []}
                      anchor={`option-${idx}`}
                    />
                    <div className="flex gap-2 items-center">
                      <input
                        type="text"
                        className="input flex-1"
                        value={option.label}
                        onChange={(e) => {
                          // Per keystroke: update the LABEL only. The internal
                          // value slug settles once, on blur -- re-minting it
                          // per keystroke churned the slug through every
                          // intermediate label (and visibly mutated the chip
                          // under the author's cursor), bd polyglot-pdf-0x10.5.
                          const newOptions = [...safeOptions(field)];
                          // A label edit invalidates the option's baked
                          // label_translations -- they translate the OLD text,
                          // and the runtime keys them by language on the option,
                          // so a renamed option would show/speak wrong-language
                          // text (bd polyglot-pdf-d25e). Drop them on the first
                          // real change (React fires onChange only when the text
                          // differs); the editor's Translate-options action or
                          // translate_option_labels.py re-bakes on demand.
                          const edited = { ...option, label: e.target.value };
                          delete edited.label_translations;
                          newOptions[idx] = edited;
                          updateField({ options: newOptions });
                        }}
                        onBlur={() => {
                          // Edit settled: mint the slug from the final label,
                          // unique across the OTHER options (the value is an
                          // internal join key, never free-typed; renaming the
                          // label is how it changes). bd h76m.10. An empty
                          // label mints nothing -- keep the old value so
                          // dependents' references stay intact.
                          const label = option.label || '';
                          if (!label.trim()) return;
                          const otherLabels = safeOptions(field)
                            .filter((_, i) => i !== idx)
                            .map(o => o.label || '');
                          const oldValue = option.value;
                          const value = mintUniqueSlugs([...otherLabels, label]).slice(-1)[0];
                          if (!value || value === oldValue) return;
                          const newOptions = [...safeOptions(field)];
                          newOptions[idx] = { ...option, value };
                          const updatedField = { ...field, options: newOptions };
                          // A dependent's show_if/require_if can reference this
                          // option by its OLD slug. Unlike Remove (which BLOCKS
                          // deleting a referenced option), rename retargets
                          // every referencing condition to the new slug
                          // atomically with the value change, keeping the
                          // schema ref-clean without freezing the field (bd
                          // polyglot-pdf-432u). Both the field's own change AND
                          // the dependents' retarget must land in ONE commit --
                          // two separate onUpdateField/onUpdateFields calls would
                          // race (the second overwrites the first's result via
                          // the undo history's functional setState) -- so when
                          // onUpdateFields is available, splice the changed field
                          // into the retargeted list and commit once; only fall
                          // back to the single-field path when it is absent (no
                          // dependents can be retargeted without it anyway).
                          if (onUpdateFields && oldValue) {
                            const withRename = schema.fields.map(f =>
                              f.id === field.id ? updatedField : f,
                            );
                            const retargeted = retargetOptionValueReferences(
                              withRename, field.id, String(oldValue), value, schema.sections,
                            );
                            onUpdateFields(retargeted.fields, retargeted.sections);
                          } else {
                            updateField({ options: newOptions });
                          }
                        }}
                        placeholder="Option label"
                      />
                      {(() => {
                        // A dependent gated on this option's slug would dangle
                        // (or, if silently stripped, flip from hidden to
                        // shown-for-everyone). Block the delete and name the
                        // dependents so the author retargets them first
                        // (Codex PR #310 round 2).
                        const referencedBy = option.value
                          ? optionValueReferencedBy(schema, field.id, String(option.value))
                          : [];
                        // A choice field (select/radio/checkbox_group) needs >= 2
                        // options in v2; removing at the floor would make a valid
                        // group unsaveable/unpromotable in one click. Structural
                        // splits go through Ungroup, not option-by-option Remove
                        // (Codex PR #310 round 3).
                        // safeOptions().length, not the RAW length (bd
                        // polyglot-pdf-8bjdx, fresh-eyes round 1): a malformed
                        // entry inflates the raw count, so a field with only 2
                        // real options read as 3 and left Remove enabled --
                        // one click away from the single-option choice field
                        // this floor exists to prevent, which the v2 backend
                        // model rejects at the promotion gate. `.length` never
                        // throws, so the crash-focused fix above did not cover
                        // this and the source-scan guard cannot see it.
                        const atFloor =
                          field.type !== 'checkbox' &&
                          safeOptions(field).length <= 2;
                        const blocked = referencedBy.length > 0 || atFloor;
                        const reason = referencedBy.length > 0
                          ? `Used by a condition on: ${referencedBy.join(', ')}. Retarget those first.`
                          : atFloor
                            ? 'A group needs at least two options. Ungroup to split it instead.'
                            : undefined;
                        return (
                          <button
                            className="btn-sm btn-secondary disabled:opacity-50"
                            disabled={blocked}
                            title={reason}
                            onClick={() => {
                              const newOptions = safeOptions(field).filter((_, i) => i !== idx);
                              updateField({ options: newOptions });
                            }}
                          >
                            Remove
                          </button>
                        );
                      })()}
                    </div>
                    {authorTier && (
                      <details className="text-xs pl-1">
                        <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
                          Advanced: PDF widget
                        </summary>
                        {/* The internal value slug lives here, out of the
                            default option row -- it is plumbing (the join key
                            conditions and the fill path match on), and showing
                            it beside the label confused editors (bd
                            polyglot-pdf-0x10.5). Author tier can still inspect
                            it; it re-mints from the label when an edit settles. */}
                        {option.value && (
                          <div className="mt-1 text-gray-500">
                            Internal value:{' '}
                            <span
                              className="font-mono bg-gray-100 rounded px-1.5 py-0.5"
                              title="Internal value (slug) -- minted from the label when editing settles, not editable"
                            >
                              {option.value}
                            </span>
                          </div>
                        )}
                        {/* A `select` has NO per-option widget concept: it
                            writes its scalar value through the field-level
                            mapping and its options never carry a widget, so
                            neither the read-only display nor the reassign
                            select applies -- render nothing (bd
                            polyglot-pdf-spcu). */}
                        {field.type === 'select' ? null :
                        /* The shared-name shape (field-level pdf_field_name +
                            option pdf_on_value) is RADIO-ONLY: a checkbox_group
                            forbids a field-level name entirely, so a
                            checkbox_group option with no own pdf_field_name is
                            genuinely UNFILLABLE, not shared-name (v2 model
                            form_models.py:821-843; outer review). Gate the
                            read-only shared-name display to radio; a
                            checkbox_group option keeps the reassign select so
                            the author can map its own widget. The discriminator
                            is per-OPTION so a MIXED radio field renders each
                            option by its true shape (bd mrdj round 2). */
                        (field.type === 'radio'
                          && !option.pdf_field_name && field.pdf_field_name) ? (
                          // SHARED-NAME radio kid: keyed by pdf_on_value against
                          // the FIELD's pdf_field_name; it must NOT gain its own
                          // pdf_field_name (both-keys trips dump-widget-
                          // multiclaim + flips the fill branch). Fixed widget,
                          // shown read-only -- no reassign select.
                          option.pdf_on_value ? (
                            <div className="mt-1 text-gray-500 font-mono">
                              widget: {field.pdf_field_name} (on: {option.pdf_on_value})
                            </div>
                          ) : (
                            // A shared-name kid with NO pdf_on_value is
                            // UNFILLABLE: the fill route requires a truthy
                            // on-state to write and silently skips it
                            // otherwise (pdf_fill_routes.py). Don't render a
                            // confident 'widget: X' line that implies it's
                            // mapped -- warn instead (bd mrdj outer review B).
                            // The on-state is set via '+ Add from PDF widgets',
                            // not editable per-option here.
                            <div className="mt-1 text-red-600" role="alert">
                              not fillable: this option needs an on-state
                              (re-add it via "+ Add from PDF widgets")
                            </div>
                          )
                        ) : (
                          // DISTINCT-name option (or an unmapped checkbox_group
                          // option): it carries -- or must acquire -- its own
                          // pdf_field_name. Reassignable among real widgets,
                          // never free text. OptionWidgetSelect shows
                          // '(no widget assigned)' for an unmapped option, which
                          // for a checkbox_group is the correct 'assign a widget'
                          // affordance (its lint ERROR flags it until mapped).
                          <OptionWidgetSelect
                            value={option.pdf_field_name || ''}
                            siblingNames={safeOptions(field)
                              .filter((_, i) => i !== idx)
                              .map(o => o.pdf_field_name)
                              .filter((n): n is string => !!n)}
                            onLoadUnclaimedWidgets={onLoadUnclaimedWidgets}
                            ariaLabel={`Option ${idx + 1} PDF widget`}
                            onChange={(name) => {
                              const newOptions = [...safeOptions(field)];
                              newOptions[idx] = { ...option, pdf_field_name: name };
                              updateField({ options: newOptions });
                            }}
                          />
                        )}
                      </details>
                    )}
                  </div>
                )))}
                {(authorTier || field.type === 'select') && (
                  <button
                    className="btn btn-secondary w-full text-sm"
                    onClick={() => {
                      const opts = safeOptions(field);
                      const value = mintUniqueSlugs(
                        [...opts.map(o => o.label || ''), 'option'],
                      ).slice(-1)[0];
                      updateField({ options: [...opts, { label: '', value }] });
                    }}
                  >
                    + Add Option
                  </button>
                )}
                {/* Add a missed checkbox/radio box from the PDF's unclaimed
                    widgets (bd nivy). Author-tier hosted only (the callback is
                    provided then); group fields only (a select's options are not
                    per-widget). */}
                {onLoadUnclaimedWidgets
                  && (field.type === 'checkbox_group' || field.type === 'radio') && (
                  <WidgetPicker
                    existingValues={safeOptions(field).map(o => o.value || '')}
                    onLoad={onLoadUnclaimedWidgets}
                    onPick={(opt, fieldPdfFieldName) =>
                      updateField({
                        options: [...safeOptions(field), opt],
                        // A shared-name group carries the widget name on the
                        // FIELD. Gate on type=radio: v2 FORBIDS a field-level
                        // pdf_field_name on a checkbox_group (form_models
                        // rejects it at the promotion gate), and a shared-name
                        // CHECKBOX matrix (widget_count>1) would otherwise lift
                        // one here -> an un-promotable schema (Opus fallback).
                        ...(fieldPdfFieldName && field.type === 'radio'
                            && !field.pdf_field_name
                          ? { pdf_field_name: fieldPdfFieldName }
                          : {}),
                      })
                    }
                  />
                )}
              </div>
            ) : (authorTier || field.type === 'select') ? (
              <button
                className="btn btn-secondary w-full"
                onClick={() =>
                  updateField({
                    options: [{ label: '', value: mintUniqueSlugs(['option'])[0] }],
                  })
                }
              >
                + Add Option
              </button>
            ) : (
              <p className="text-xs text-gray-500">No options.</p>
            )}
          </div>
        )}

        {/* Debug Info -- author-tier only: the raw dump exposes every
            option's pdf_field_name (the widget plumbing the per-option
            Advanced disclosure gates), so an editor-tier contractor must not
            see it either (Codex PR #310). */}
        {authorTier && (
          <details className="text-xs">
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
              Advanced / Debug
            </summary>
            <pre className="mt-2 p-2 bg-gray-100 rounded overflow-auto text-xs">
              {JSON.stringify(field, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
};
