import React from 'react';

// First-run guide for hosted (contractor) sessions -- a dismissable 3-step
// overlay shown once per browser, re-openable from the header's Help button
// (bd 92qe.5). Persistence is best-effort: storage can throw in restricted
// contexts, in which case the guide simply shows again next visit.

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
}

const STEPS: Array<{ title: string; body: string }> = [
  {
    title: '1. Pick a form',
    body:
      'Choose a form card from the catalogue at the top. Its PDF loads on the ' +
      "left, the field list in the middle, and the selected field's " +
      'properties on the right.',
  },
  {
    title: '2. Fix the fields that need attention',
    body:
      'Yellow and red icons mark fields needing review. Click "Next to ' +
      'review" (or press N) to jump to the next one; arrow keys move through ' +
      'the list, Esc deselects. Green means done.',
  },
  {
    title: '3. Save, then mark it complete',
    body:
      'Cmd+S (Ctrl+S) saves back to the shared workspace. When every field ' +
      "is green, click \"Mark complete\" on the form's card so the " +
      'maintainer can publish it.',
  },
];

export const HostedGuide: React.FC<HostedGuideProps> = ({ onClose }) => {
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
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6">
        <div className="flex items-start justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Welcome! Here is the flow
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
        <ol className="space-y-4">
          {STEPS.map(step => (
            <li key={step.title}>
              <h3 className="text-sm font-semibold text-gray-900">{step.title}</h3>
              <p className="text-sm text-gray-600">{step.body}</p>
            </li>
          ))}
        </ol>
        <div className="mt-6 flex justify-end">
          <button type="button" className="btn btn-primary" onClick={close}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
};
