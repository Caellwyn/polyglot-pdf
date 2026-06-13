// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { DisclaimerModal, DISCLAIMER_TRANSLATIONS } from './DisclaimerModal';

describe('DisclaimerModal', () => {
    afterEach(() => {
        cleanup();
    });

    const defaultProps = {
        isOpen: true,
        selectedLanguage: 'English',
        onListenAgain: vi.fn(),
        onAgree: vi.fn(),
    };

    // Body-copy coverage RESTORED (Codex review, PR #122): the disclaimer is the
    // mandatory legal notice, so its warning text must stay asserted -- skipping
    // would let a dropped/mistranslated paragraph pass green. The old assertions
    // failed only because the copy was rewritten to the current legal-grade text
    // (bd polyglot-pdf-pwt); each substring below is checked against the current
    // copy. The paragraph is one long text node, so we assert on the rendered
    // document's textContent (a getByText "node" match would resolve up the whole
    // ancestor chain and report "multiple elements"). T1.3 (polyglot-pdf-uov.6)
    // still owns the full disclaimer spec audit.
    const assertBodyText = (needle: string) =>
        expect(document.body.textContent).toContain(needle);

    it('renders English body copy by default', () => {
        render(<DisclaimerModal {...defaultProps} />);
        expect(screen.getByText('Important Notice')).toBeTruthy();
        assertBodyText('It helps you fill out a form');
        expect(screen.getByText('I Agree')).toBeTruthy();
    });

    it('renders Spanish body copy when selectedLanguage is Spanish', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Spanish" />);
        expect(screen.getByText('Aviso Importante')).toBeTruthy();
        assertBodyText('Le ayuda a completar un formulario');
        expect(screen.getByText('Estoy de Acuerdo')).toBeTruthy();
    });

    it('renders Chinese body copy when selectedLanguage is Chinese', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Chinese" />);
        // ASCII-only source (scar #6 / AGENTS.md): the Chinese assertion strings are
        // written as \u escapes, never raw glyphs. JS decodes them at parse time to
        // the same characters the modal renders, so coverage is unchanged. Escapes:
        // title = zh "Important Notice", body = zh "It helps you fill out a form",
        // agree button = zh "I Agree".
        expect(screen.getByText('\u91cd\u8981\u901a\u77e5')).toBeTruthy();
        assertBodyText('\u5b83\u5e2e\u52a9\u60a8\u586b\u5199\u8868\u683c');
        expect(screen.getByText('\u6211\u540c\u610f')).toBeTruthy();
    });

    it('falls back to English for unknown languages', () => {
        render(<DisclaimerModal {...defaultProps} selectedLanguage="Klingon" />);
        expect(screen.getByText('Important Notice')).toBeTruthy();
        expect(screen.getByText('I Agree')).toBeTruthy();
    });

    it('does not render when isOpen is false', () => {
        render(<DisclaimerModal {...defaultProps} isOpen={false} />);
        expect(screen.queryByText('Important Notice')).toBeNull();
    });

    it('calls onAgree when agree button is clicked', () => {
        render(<DisclaimerModal {...defaultProps} />);
        fireEvent.click(screen.getByText('I Agree'));
        expect(defaultProps.onAgree).toHaveBeenCalled();
    });

    it('calls onListenAgain when listen again button is clicked', () => {
        render(<DisclaimerModal {...defaultProps} />);
        fireEvent.click(screen.getByText('Listen Again'));
        expect(defaultProps.onListenAgain).toHaveBeenCalled();
    });
});

// =====================================================================
// T1.3 (bd polyglot-pdf-uov.6): the BROADER disclaimer spec audit.
//
// The block above (PR #122) asserts the 3 English/Spanish/Chinese body-copy
// substrings and the 4 open/close/agree/listen-again behaviors. This block
// covers the remaining scope the bead names: (a) coverage parity across ALL
// translated languages -- not just the 3 -- so a dropped or English-fallback
// entry in any of the other ~15 is caught; (b) the p1/p2/p3-vs-fullText
// rendering distinction; (c) accessibility + modal behavior beyond the 4.
//
// The disclaimer is a mandatory legal notice shown before any form work, so
// these are spec-tests of a load-bearing legal surface: every supported
// language must show ITS OWN notice (an English fallback for a non-English
// user is a real defect), and the visual paragraphs shown must be the p1/p2/p3
// the component renders -- never the longer fullText (that string is the
// audio/TTS script, read aloud by VoiceOverlay, not painted in the modal).
//
// ASCII-only source (scar #6 / AGENTS.md): no assertion hardcodes a
// non-Latin glyph. Per-language checks read the EXPECTED text from the
// exported DISCLAIMER_TRANSLATIONS map (the same data the component renders)
// rather than re-typing each translation, so the test stays ASCII and cannot
// drift from the source copy.
// =====================================================================
describe('DisclaimerModal -- full spec audit (T1.3 / bd polyglot-pdf-uov.6)', () => {
    afterEach(() => {
        cleanup();
    });

    const baseProps = {
        isOpen: true,
        onListenAgain: vi.fn(),
        onAgree: vi.fn(),
    };

    // The full supported set, derived from the exported map (NOT a hardcoded
    // list) so adding a language to the component automatically extends the
    // audit. Drop English: it is the fallback, so "renders its own title, not
    // the English fallback" is vacuous for it -- it has dedicated tests above.
    const ALL_LANGUAGES = Object.keys(DISCLAIMER_TRANSLATIONS);
    const NON_ENGLISH = ALL_LANGUAGES.filter((lang) => lang !== 'English');

    describe('coverage parity: every supported language renders ITS OWN notice', () => {
        it('exposes more than the 3 spot-checked languages', () => {
            // Guards the audit's premise: if the map ever shrank to <=3 entries
            // the per-language loop below would silently cover almost nothing.
            expect(ALL_LANGUAGES.length).toBeGreaterThan(3);
            expect(ALL_LANGUAGES).toContain('English');
        });

        it.each(NON_ENGLISH)(
            'renders the %s title from its own translation (not the English fallback)',
            (language) => {
                const expected = DISCLAIMER_TRANSLATIONS[language];
                render(<DisclaimerModal {...baseProps} selectedLanguage={language} />);

                // The title for a non-English language must be that language's
                // own title. Since every language has a DISTINCT title, finding
                // it proves the entry was wired (not silently English-fallen-back).
                expect(screen.getByText(expected.title)).toBeTruthy();
                // And the English title must NOT appear for a non-English user
                // whose own title differs (every non-English title here does).
                expect(expected.title).not.toBe(DISCLAIMER_TRANSLATIONS['English'].title);
                expect(screen.queryByText(DISCLAIMER_TRANSLATIONS['English'].title)).toBeNull();
            }
        );

        it.each(NON_ENGLISH)(
            'renders the first paragraph of the %s notice', (language) => {
                const expected = DISCLAIMER_TRANSLATIONS[language];
                render(<DisclaimerModal {...baseProps} selectedLanguage={language} />);
                expect(document.body.textContent).toContain(expected.p1);
            }
        );
    });

    describe('rendering distinction: the modal shows p1/p2/p3, never fullText', () => {
        it('renders all three visual paragraphs (p1, p2, p3) for English', () => {
            const en = DISCLAIMER_TRANSLATIONS['English'];
            render(<DisclaimerModal {...baseProps} selectedLanguage="English" />);
            const body = document.body.textContent || '';
            expect(body).toContain(en.p1);
            expect(body).toContain(en.p2);
            expect(body).toContain(en.p3);
        });

        it('does NOT paint the fullText audio script verbatim in the modal', () => {
            // fullText is the spoken/TTS version (consumed by VoiceOverlay), a
            // SUPERSET of p1+p2+p3 concatenated WITHOUT the paragraph breaks the
            // modal renders. The component maps p1/p2/p3 into three <p> nodes, so
            // the single-string fullText -- which contains a p1->p2 junction with
            // no break -- must not appear as one contiguous run in the DOM.
            const en = DISCLAIMER_TRANSLATIONS['English'];
            render(<DisclaimerModal {...baseProps} selectedLanguage="English" />);
            const body = document.body.textContent || '';
            // The exact fullText string is not a contiguous substring of the
            // rendered modal (the paragraphs are separate text nodes).
            expect(body).not.toContain(en.fullText);
            // Sanity: fullText really is the longer audio script (superset of p1).
            expect(en.fullText.length).toBeGreaterThan(en.p1.length);
            expect(en.fullText).toContain(en.p1);
        });
    });

    describe('data integrity of DISCLAIMER_TRANSLATIONS (the public contract)', () => {
        it.each(ALL_LANGUAGES)(
            '%s has all five non-empty fields (title, p1, p2, p3, fullText)',
            (language) => {
                const t = DISCLAIMER_TRANSLATIONS[language];
                for (const key of ['title', 'p1', 'p2', 'p3', 'fullText'] as const) {
                    expect(typeof t[key]).toBe('string');
                    expect(t[key].trim().length).toBeGreaterThan(0);
                }
            }
        );

        it.each(ALL_LANGUAGES)(
            '%s fullText is the audio superset: it contains p1, p2, and p3',
            (language) => {
                const t = DISCLAIMER_TRANSLATIONS[language];
                // The audio script reads the whole notice, so each visual
                // paragraph's text appears within fullText. This catches a
                // translation where the spoken and visual copy drifted apart.
                expect(t.fullText).toContain(t.p1);
                expect(t.fullText).toContain(t.p2);
                expect(t.fullText).toContain(t.p3);
            }
        );
    });

    describe('accessibility + modal behavior', () => {
        it('exposes the modal as an aria dialog labelled by its title', () => {
            render(<DisclaimerModal {...baseProps} selectedLanguage="English" />);
            const dialog = screen.getByRole('dialog');
            expect(dialog.getAttribute('aria-modal')).toBe('true');
            // aria-labelledby must point at the rendered title element's id.
            const labelledBy = dialog.getAttribute('aria-labelledby');
            expect(labelledBy).toBeTruthy();
            const title = document.getElementById(labelledBy as string);
            expect(title?.textContent).toBe(DISCLAIMER_TRANSLATIONS['English'].title);
        });

        it('locks body scroll while open and restores it on close', () => {
            const { rerender } = render(
                <DisclaimerModal {...baseProps} isOpen={true} selectedLanguage="English" />
            );
            expect(document.body.style.overflow).toBe('hidden');

            rerender(
                <DisclaimerModal {...baseProps} isOpen={false} selectedLanguage="English" />
            );
            expect(document.body.style.overflow).toBe('');
        });

        it('suppresses the Escape key (modal is not ESC-dismissable)', () => {
            const onAgree = vi.fn();
            const onListenAgain = vi.fn();
            render(
                <DisclaimerModal
                    isOpen={true}
                    selectedLanguage="English"
                    onAgree={onAgree}
                    onListenAgain={onListenAgain}
                />
            );

            // The modal installs a capture-phase Escape handler that
            // preventDefault/stopPropagation; pressing Escape must neither
            // dismiss the dialog nor fire either callback.
            fireEvent.keyDown(document, { key: 'Escape', code: 'Escape' });

            expect(screen.getByRole('dialog')).toBeTruthy();
            expect(onAgree).not.toHaveBeenCalled();
            expect(onListenAgain).not.toHaveBeenCalled();
        });
    });
});
