// @vitest-environment node
//
// The dft1 pieces must actually be MOUNTED (bd polyglot-pdf-dft1).
//
// Every piece of this feature has its own passing unit tests, and for a while
// NONE of them was reachable by a client: ten well-tested modules, zero mounted.
// That is the failure this project has paid for repeatedly -- a guard nobody
// calls, a helper nobody renders -- and unit tests cannot see it by
// construction.
//
// Derived from the shipped source so unmounting reddens here.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Anchor on the vitest ROOT rather than __dirname, which vitest rewrites (it
// resolved one directory short, so every assertion below failed on ENOENT --
// including ones that were true). process.cwd() is the frontend package dir.
const SRC = resolve(process.cwd(), 'src');

function read(relative: string): string {
  return readFileSync(resolve(SRC, relative), 'utf-8');
}

describe('dft1 wiring', () => {
  it('the overlay RENDERS the save nudge', () => {
    const overlay = read('demo/VoiceOverlay.tsx');
    expect(overlay).toContain('<SaveNudge');
    expect(overlay).toContain('useSaveNudge(');
  });

  it('the nudge is scoped to CLIENT sessions', () => {
    // Staff have their own machines and their own workflow. Nudging them is
    // noise; nudging a client is the difference between keeping and losing
    // their work.
    const overlay = read('demo/VoiceOverlay.tsx');
    expect(overlay).toContain('hasClientLinkToken()');
    expect(overlay).toMatch(/enabled:\s*isClientSession/);
  });

  it('the nudge SPEAKS through the free notice route', () => {
    // Not the paid TTS route: that one redeems the link, so it would answer
    // the budget-exhausted client with silence and burn a live client's link
    // to deliver our own warning.
    const overlay = read('demo/VoiceOverlay.tsx');
    expect(overlay).toContain('createNoticeSpeaker');
    expect(overlay).toContain('speak={speakNotice}');
    expect(overlay).not.toContain('/api/tts/spellback');
  });

  it('the ENDING notice is used when voice is ending', () => {
    const overlay = read('demo/VoiceOverlay.tsx');
    expect(overlay).toContain('NOTICE_VOICE_ENDING');
    expect(overlay).toContain('NOTICE_SAVE_EARLY');
  });

  it('the fill request still carries the resume stamp', () => {
    // Without this the saved PDF has no identity and cannot be resumed --
    // and the backend half would stay perfectly green while it happened.
    const filler = read('schema-forms/utils/pdfFiller.ts');
    expect(filler).toContain('form_session_id');
    const form = read('schema-forms/components/SchemaForm.tsx');
    expect(form).toContain('state.formSessionId');
  });

  it('both download paths are stamped, and the preview is deliberately not', () => {
    // Enumerate the set rather than trusting a spot check: download and print
    // produce files the client KEEPS; the preview renders a blob that is
    // revoked when the modal closes.
    const form = read('schema-forms/components/SchemaForm.tsx');
    const stamped = form.split('state.formSessionId').length - 1;
    expect(stamped).toBe(2);

    const preview = read('pdf-view/FilledPreviewModal.tsx');
    expect(preview).toContain('NO resume stamp here');
  });

  it('the overlay RENDERS the resume choice', () => {
    const overlay = read('demo/VoiceOverlay.tsx');
    expect(overlay).toContain('<ResumeUpload');
    expect(overlay).toContain('applyResume(');
  });

  it('the resume choice comes BEFORE the disclaimer', () => {
    // A client resuming should choose "continue my saved form" and THEN
    // agree, so the acceptance record belongs to the session they are about
    // to work in -- not to one that ended days ago.
    const overlay = read('demo/VoiceOverlay.tsx');
    expect(overlay.indexOf('<ResumeUpload')).toBeLessThan(
      overlay.indexOf('<DisclaimerModal'),
    );
  });

  it('a resumed session RE-ACCEPTS the disclaimer', () => {
    // applyResume clears the flag; if that ever stopped, a resumed client
    // would skip the agreement entirely and the audit trail would carry a
    // tick from a session that ended who knows when.
    const apply = read('schema-forms/applyResume.ts');
    expect(apply).toContain('disclaimerAccepted: false');
  });

  it('the resume upload is verified SERVER-side, not in the browser', () => {
    // A client-side check is defeated by a client-side attacker.
    const component = read('schema-forms/components/ResumeUpload.tsx');
    expect(component).toContain('/api/resume-form');
  });
});
