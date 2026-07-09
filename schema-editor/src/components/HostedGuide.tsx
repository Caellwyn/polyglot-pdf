import React from 'react';
import type { EditorRole } from '../utils/remoteKitStore';

// In-app guided help for the schema editor (bd 92qe.5, expanded). A sectioned,
// navigable overlay -- a left rail of section links plus a scrolling content
// pane -- covering the full contractor workflow (getting around, field
// properties, common tasks, extraction, saving, troubleshooting). It is
// tier-aware: author-only sections (extraction) render only for role 'author'.
//
// It is shown once per browser on first hosted visit, and re-openable any time
// from the header's Help button. Persistence is best-effort: storage can throw
// in restricted contexts, in which case the guide simply shows again next visit.

const GUIDE_SEEN_KEY = 'schema-editor.guideSeen';

export function hasSeenGuide(): boolean {
  try {
    return window.localStorage.getItem(GUIDE_SEEN_KEY) === '1';
  } catch {
    return false;
  }
}

export function markGuideSeen(): void {
  try {
    window.localStorage.setItem(GUIDE_SEEN_KEY, '1');
  } catch {
    // Best-effort only.
  }
}

interface HostedGuideProps {
  onClose: () => void;
  // Access tier for the current session. When 'author', author-only sections
  // (extraction) are shown. In local mode this is null and author-only sections
  // are hidden (local authoring uses the terminal extractor, not this button).
  role?: EditorRole | null;
}

interface GuideSection {
  id: string;
  title: string;
  authorOnly?: boolean;
  body: React.ReactNode;
}

// Small presentational helpers -- keep the section copy readable below.
const P: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-sm text-gray-600 leading-relaxed">{children}</p>
);
const H: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h4 className="text-sm font-semibold text-gray-900 mt-4 first:mt-0">
    {children}
  </h4>
);
const UL: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ul className="list-disc pl-5 space-y-1 text-sm text-gray-600">{children}</ul>
);
// A UI label / button name as it appears on screen.
const K: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="font-semibold text-gray-800">{children}</span>
);

const SECTIONS: GuideSection[] = [
  {
    id: 'quick-start',
    title: 'Quick start',
    body: (
      <>
        <P>
          Three steps to review a form. Everything else in this guide is detail
          on these.
        </P>
        <UL>
          <li>
            <K>Pick a form</K> from the catalogue at the top. Its PDF opens on
            the left, the field list in the middle, and the selected field's
            properties on the right; the validation and preview panels sit below.
          </li>
          <li>
            <K>Fix the fields that need attention.</K> Yellow and red icons mark
            fields that still need work; green means done. Click{' '}
            <K>Next to review</K> (or press <K>N</K>) to jump to the next one.
          </li>
          <li>
            <K>Save, then mark it complete.</K> Press <K>Cmd+S</K> (
            <K>Ctrl+S</K>) to save. When every field is green, click{' '}
            <K>Mark complete</K> on the form's card so the maintainer can publish
            it.
          </li>
        </UL>
      </>
    ),
  },
  {
    id: 'getting-around',
    title: 'Getting around',
    body: (
      <>
        <H>Finding a field</H>
        <UL>
          <li>
            Use the <K>Search fields...</K> box above the field list to filter by
            id, spoken name, or PDF field name.
          </li>
          <li>
            <K>Next to review</K> (or <K>N</K>) jumps to the next field that
            still needs work, wrapping past the end.
          </li>
          <li>
            <K>Arrow Up</K> / <K>Arrow Down</K> step through the list;{' '}
            <K>Esc</K> deselects and shows the form-level panel. (These do not
            fire while you are typing in a box.)
          </li>
          <li>
            Section headers expand and collapse. Status icons show completion at
            a glance: <K>green</K> = done, <K>yellow</K> = needs review,{' '}
            <K>red</K> = has an error.
          </li>
        </UL>
        <H>Reading the PDF</H>
        <UL>
          <li>
            Page arrows and the page box move between pages; <K>Fit Width</K> /{' '}
            <K>Fit Page</K> and the <K>+</K> / <K>-</K> buttons control zoom.
          </li>
          <li>
            Fields are outlined on the PDF in the same green/yellow/red colors.
            Click an outline to select that field; it highlights in the list and
            opens in the editor too.
          </li>
        </UL>
      </>
    ),
  },
  {
    id: 'field-properties',
    title: 'Field properties',
    body: (
      <>
        <P>
          The right-hand panel edits the selected field, top to bottom. The
          headings below match what you see on screen.
        </P>
        <H>Basic Properties</H>
        <UL>
          <li>
            <K>Field Type</K> -- text, date, radio, checkbox, and so on. For a
            grouped field this is locked; you change it with Merge / Ungroup (see
            Common tasks), not here.
          </li>
          <li>
            <K>Spoken Name</K> -- a user-friendly name for the voice AI (for
            example "alien registration number").
          </li>
          <li>
            <K>Section</K> -- which section the field belongs to. Changing this
            dropdown is how you move a field to another section.
          </li>
          <li>
            <K>Required</K> -- the user must answer before the form is done.
          </li>
          <li>
            <K>Read Only</K> -- the value is shown but the user cannot change it
            (unless a control unlocks it).
          </li>
          <li>
            <K>Hidden</K> -- the field is not shown at all (unless a control
            reveals it).
          </li>
        </UL>
        <H>Help &amp; Guidance -- Instructions and Format Hint</H>
        <P>
          These two are the most important thing you write, and they are commonly
          misunderstood. They are <K>guidance for the voice AI</K> -- how the
          assistant coaches the user through the field. They are NOT a caption
          printed on the paper form.
        </P>
        <UL>
          <li>
            <K>Instructions</K> -- what the AI should tell or ask the user for
            this field: what it means, and where to find the answer. Write it the
            way you would explain the field to a person who has never seen the
            form.
          </li>
          <li>
            <K>Format Hint</K> -- a short shape example, like "7-9 digits" or
            "MM/DD/YYYY". The AI uses it to steer the user and to sanity-check the
            answer.
          </li>
        </UL>
        <P>
          Good Instructions: "Your alien registration number (A-Number) is a 7-9
          digit number found on your green card; it begins with an 'A'." Poor
          Instructions: "[TODO: add help text]". The extraction step often
          drafts these for you (see Extraction); your job is to make them clear
          and correct.
        </P>
        <H>Validation</H>
        <UL>
          <li>
            <K>Format Preset</K> -- a named validator (for example a_number, ssn,
            email).
          </li>
          <li>
            <K>Pattern (Regex)</K> -- a regular expression the answer must match,
            for example <code>^\d{'{7,9}'}$</code>.
          </li>
          <li>
            <K>Min Length</K> / <K>Max Length</K> -- length limits (shown for
            text fields).
          </li>
        </UL>
      </>
    ),
  },
  {
    id: 'common-tasks',
    title: 'Common tasks',
    body: (
      <>
        <H>Re-order fields</H>
        <P>
          Drag the handle (the six-dot grip) on a field row up or down. Fields
          re-order within their own section.
        </P>
        <H>Move a field to another section</H>
        <P>
          Select the field and change the <K>Section</K> dropdown in Basic
          Properties.
        </P>
        <H>Required, Read Only, Hidden</H>
        <P>
          The three checkboxes in Basic Properties. <K>Required</K> forces an
          answer; <K>Read Only</K> shows a value the user cannot edit;{' '}
          <K>Hidden</K> keeps the field out of the flow. A control (below) can
          flip any of these at runtime.
        </P>
        <H>Add conditional logic (show / hide a field)</H>
        <P>
          Select the field that should appear conditionally, open{' '}
          <K>Conditional Logic</K>, and use the <K>Shown when</K> builder:{' '}
          <K>+ Add condition</K>, pick a trigger field, choose an operator ("is",
          "is not", "is checked", "contains", ...), and enter the value. The{' '}
          <K>all of</K> / <K>at least one of</K> / <K>none of</K> buckets combine
          multiple rows. The <K>Required when</K> builder works the same way but
          controls whether the field is required.
        </P>
        <H>Field controls (this field changes others)</H>
        <P>
          On the field that does the driving (a checkbox, a Yes/No radio), open{' '}
          <K>Controls Fields</K> and click <K>+ Add Control</K>. Set the
          operator and value that trigger the rule, then tick the target fields
          under <K>Shows</K>, <K>Hides</K>, <K>Unlocks</K>, <K>Locks</K>,{' '}
          <K>Makes required</K>, or <K>Makes optional</K>. Example: a "Filing for
          someone else?" checkbox whose checked value <K>Unlocks</K> the
          representative-name fields.
        </P>
        <H>Checkbox groups and radio consolidation</H>
        <P>
          A set of separate checkboxes that should be one choice can be merged:
          in the field list, tick two or more checkbox/radio fields (they must be
          in the same section), then click <K>Merge (several)</K> for a
          multi-select checkbox group, or <K>Merge (exactly one)</K> for a
          single-choice radio. To reverse it, select the group and click{' '}
          <K>Ungroup</K> in the editor.
        </P>
        <H>Options (radio / select / checkbox group)</H>
        <P>
          Edit each option's <K>label</K>; the value chip beside it is an
          auto-generated slug and is read-only. Use <K>+ Add Option</K> and{' '}
          <K>Remove</K> to change the list. Author-tier contractors also get{' '}
          <K>Add from PDF widgets</K> to pull options straight from the form's
          unclaimed checkboxes.
        </P>
      </>
    ),
  },
  {
    id: 'extraction',
    title: 'Extraction',
    authorOnly: true,
    body: (
      <>
        <P>
          Extraction turns a blank fillable PDF into a first-draft schema you can
          then review. It is an author-tier task.
        </P>
        <H>1. Add a form (PDF)</H>
        <P>
          Click <K>Add a form (PDF)</K> in the catalogue and pick a blank
          AcroForm PDF. This creates a draft kit with no schema yet.
        </P>
        <H>2. Attach the official instructions PDF (do this whenever one exists)</H>
        <P>
          Before running extraction, click <K>+ instructions PDF</K> on the new
          card and attach the form's official instructions document (the guide
          the issuing agency publishes alongside the form).
        </P>
        <P>
          This matters a lot. The extractor reads that instructions PDF and, for
          each field, finds the most specific matching passage and folds it into
          that field's <K>Instructions</K> help text (on top of any tooltip the
          form itself carries). It saves you from re-typing guidance field by
          field, and it gives the voice AI far richer per-field help from the
          start -- so your review is polishing good drafts instead of writing
          from scratch. It is optional and degrades gracefully: if you skip it or
          the file is unreadable, extraction still runs on the form alone.
        </P>
        <H>3. Run extraction</H>
        <P>
          Click <K>Run extraction</K>. It runs on the server and takes a few
          minutes (the button shows an elapsed counter). When it finishes it
          reports how many fields were found and any issues to repair. Open the
          kit and review it -- extraction is a starting point, not a finished
          schema.
        </P>
      </>
    ),
  },
  {
    id: 'saving',
    title: 'Saving & finishing',
    body: (
      <>
        <UL>
          <li>
            <K>Cmd+S</K> / <K>Ctrl+S</K> saves your changes to the shared
            workspace. The header shows <K>Saving...</K> then <K>Saved</K>.
          </li>
          <li>
            <K>Undo</K> / <K>Redo</K> -- <K>Cmd+Z</K> and{' '}
            <K>Cmd+Shift+Z</K> (Ctrl on Windows/Linux).
          </li>
          <li>
            <K>Mark complete</K> on a form's card promotes it. Save first -- the
            button uses your last saved version. The server validates the schema
            and refuses a broken one with the reason.
          </li>
          <li>
            Completed forms ship to the voice app on the maintainer's next
            deploy. A draft stays in the workspace and is not published.
          </li>
        </UL>
      </>
    ),
  },
  {
    id: 'troubleshooting',
    title: 'When something looks wrong',
    body: (
      <>
        <UL>
          <li>
            The <K>Validation &amp; Progress</K> panel shows the completion bar
            and how many fields are complete, need review, or total. Click any
            listed error to jump straight to its field.
          </li>
          <li>
            Author tier: a <K>Repair all</K> button appears when there are
            fixable issues (it mints missing option slugs, drops dead conditions,
            and similar).
          </li>
          <li>
            If a save fails you'll see a red banner. Your work and the open form
            are untouched -- fix the issue (or dismiss it) and save again.
          </li>
        </UL>
      </>
    ),
  },
];

export const HostedGuide: React.FC<HostedGuideProps> = ({ onClose, role }) => {
  const sections = React.useMemo(
    () => SECTIONS.filter(s => !s.authorOnly || role === 'author'),
    [role]
  );
  const [activeId, setActiveId] = React.useState(sections[0]?.id ?? '');
  // Keep the active section valid if the visible set changes (e.g. role load).
  React.useEffect(() => {
    if (!sections.some(s => s.id === activeId)) {
      setActiveId(sections[0]?.id ?? '');
    }
  }, [sections, activeId]);

  const active = sections.find(s => s.id === activeId) ?? sections[0];

  const close = () => {
    markGuideSeen();
    onClose();
  };
  // Escape closes the overlay (modal convention). Capture phase + a consumed
  // default so FieldList's window listener doesn't ALSO deselect the field
  // behind the modal (it honors e.defaultPrevented; Opus review, PR #284).
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      close();
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Getting started guide"
    >
      <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[85vh] flex flex-col">
        <div className="flex items-start justify-between p-6 pb-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            Schema Editor -- help &amp; guide
          </h2>
          <button
            type="button"
            onClick={close}
            aria-label="Close guide"
            className="text-gray-400 hover:text-gray-600"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>

        <div className="flex flex-1 min-h-0">
          {/* Section rail */}
          <nav
            className="w-48 shrink-0 border-r border-gray-200 p-3 overflow-y-auto"
            aria-label="Guide sections"
          >
            <ul className="space-y-1">
              {sections.map(s => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setActiveId(s.id)}
                    aria-current={s.id === active?.id ? 'true' : undefined}
                    className={
                      'w-full text-left px-3 py-2 rounded text-sm ' +
                      (s.id === active?.id
                        ? 'bg-primary-50 text-primary-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-100')
                    }
                  >
                    {s.title}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          {/* Content pane */}
          <div className="flex-1 min-w-0 overflow-y-auto p-6">
            {active && (
              <section aria-label={active.title}>
                <h3 className="text-base font-semibold text-gray-900 mb-3">
                  {active.title}
                </h3>
                <div className="space-y-2">{active.body}</div>
              </section>
            )}
          </div>
        </div>

        <div className="flex justify-end p-4 border-t border-gray-200">
          <button type="button" className="btn btn-primary" onClick={close}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
};
