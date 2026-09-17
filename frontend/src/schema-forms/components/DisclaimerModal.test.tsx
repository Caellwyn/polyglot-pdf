// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DisclaimerModal, DISCLAIMER_TRANSLATIONS } from './DisclaimerModal';
import { renderIntroParagraphs } from '../../shared/introScript';
import introScript from '../../shared/introScript.json';

const __dirname = dirname(fileURLToPath(import.meta.url));

// DERIVED from the shipped script store, never hand-listed: the language set
// is growing toward ~90 and a typed list rots silently (repo scar tissue).
//
// NAMED for its SOURCE, not `SPOKEN_LANGUAGES` (bd polyglot-pdf-cnwz). It used
// to shadow that real export, which made this file read as though it were
// anchored to the canonical language list when it was anchored to introScript
// -- and every assertion below that pairs it with DISCLAIMER_TRANSLATIONS was
// self-referential in the same way. The canonical anchor now lives in
// shared/translationMapLockstep.test.ts, which asserts DISCLAIMER_TRANSLATIONS
// (and every sibling map) covers exactly SPOKEN_LANGUAGES. This constant keeps
// its narrower job: the languages the intro SCRIPT ships.
const INTRO_SCRIPT_LANGUAGES = Object.keys(
    (introScript as { languages: Record<string, unknown> }).languages,
);

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

        it('every language has a UNIQUE first paragraph (the per-language anchor)', () => {
            // The per-language render check below proves "this language's OWN
            // content rendered" by asserting its p1 -- which only works if p1 is
            // distinct across languages. Titles are NOT a safe anchor: Spanish and
            // Portuguese share the title 'Aviso Importante', so a Portuguese ->
            // Spanish misroute would still render the expected title. p1, by
            // contrast, is unique per language; assert that invariant up front so
            // the anchor the loop relies on is guaranteed.
            const p1s = ALL_LANGUAGES.map((lang) => DISCLAIMER_TRANSLATIONS[lang].p1);
            expect(new Set(p1s).size).toBe(p1s.length);
        });

        it.each(NON_ENGLISH)(
            'renders the %s notice from its own translation (not the English fallback)',
            (language) => {
                const expected = DISCLAIMER_TRANSLATIONS[language];
                render(<DisclaimerModal {...baseProps} selectedLanguage={language} />);

                // Its own title renders. (Title alone is a weak anchor -- some
                // languages share a title, e.g. Spanish/Portuguese 'Aviso
                // Importante' -- so the p1 assertion below is what actually proves
                // THIS language's content rendered, not another's.)
                expect(screen.getByText(expected.title)).toBeTruthy();

                // Its own first paragraph renders. p1 is unique per language (see
                // the invariant test above), so finding it proves the entry was
                // wired to THIS language -- not silently English-fallen-back AND
                // not misrouted to a same-title sibling (the Portuguese->Spanish
                // case the title check cannot catch).
                expect(document.body.textContent).toContain(expected.p1);

                // No language here shares the ENGLISH title, so the English
                // fallback title must be absent for every non-English user.
                expect(expected.title).not.toBe(DISCLAIMER_TRANSLATIONS['English'].title);
                expect(screen.queryByText(DISCLAIMER_TRANSLATIONS['English'].title)).toBeNull();
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

        it('actively suppresses the Escape key (calls preventDefault on it)', () => {
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

            // The modal installs a capture-phase keydown handler that calls
            // preventDefault() on Escape (so a parent ESC-to-dismiss can't fire).
            // Dispatch a REAL cancelable KeyboardEvent and assert defaultPrevented
            // flipped to true -- this fails if the handler is removed, unlike a
            // plain "dialog still present" check (the modal has no native ESC
            // dismissal, so its mere presence proves nothing). This is the
            // mutation-catching assertion for the suppression behavior.
            const escEvent = new KeyboardEvent('keydown', {
                key: 'Escape',
                code: 'Escape',
                bubbles: true,
                cancelable: true,
            });
            document.dispatchEvent(escEvent);
            expect(escEvent.defaultPrevented).toBe(true);

            // And Escape neither dismisses the dialog nor fires a callback.
            expect(screen.getByRole('dialog')).toBeTruthy();
            expect(onAgree).not.toHaveBeenCalled();
            expect(onListenAgain).not.toHaveBeenCalled();
        });
    });
});

// ===========================================================================
// The UNDERTAKING register is load-bearing (bd polyglot-pdf-rtyia, register
// settled by the maintainer 2026-08-19 in bd polyglot-pdf-nsb4y)
// ===========================================================================
//
// docs/standards/confirmation-and-audit.md ("The deployment invariant") pins
// three registers and which are LIVE. ONE SOURCE is what makes that table
// true now: what the modal RENDERS and what the model SPEAKS both come from
// intro_script.json via renderIntroParagraphs, so a reader and a listener
// accept the SAME terms behind the same Agree button.
//
//   1. DISCLAIMER_TRANSLATIONS is RETIRED as body text. It survives as the
//      modal TITLE source and as a fallback for a caller that passes no
//      introParagraphs. No app code renders or speaks its p1/p2/p3/fullText.
//   2. The shipped register is the UNDERTAKING -- "you agree to review the
//      completed document yourself and with a certified professional before
//      filing" -- not the advisory "we strongly advise". Reverting to the
//      advisory copy on EITHER surface reintroduces two legal registers
//      behind one button, which is the bug nsb4y fixed.
//
// WHY THE PINS BELOW LOOK THE WAY THEY DO. Guarding this by scanning source
// for ".fullText" is NOT enough: fresh-eyes round 1 defeated exactly that with
// `const { fullText } = DISCLAIMER_TRANSLATIONS[...]`, which reintroduced the
// advisory register on the SPOKEN half with the whole suite green. The
// behavioral pins live in VoiceOverlay.disclaimer.test.tsx and assert the
// VALUE handed to readDisclaimer plus the text on SCREEN. The source scan
// here is a cheap second layer, not the guarantee.
//
// The SI carries the matching register note (backend/config.py): review is
// contractually REQUIRED and the applicant now UNDERTAKES it, but we still do
// not promise a review WILL happen -- we do not control that. bd rdsl is the
// precedent: the SI once PROMISED review where the disclaimer only advised
// it, and that survived the author, the tests and two review rounds.
describe('DISCLAIMER_TRANSLATIONS register (bd polyglot-pdf-rtyia, nsb4y)', () => {
    const languages = Object.keys(DISCLAIMER_TRANSLATIONS);

    it('ships a disclaimer for every language, each with a spoken fullText', () => {
        expect(languages.length).toBeGreaterThan(1);
        for (const lang of languages) {
            const t = DISCLAIMER_TRANSLATIONS[lang];
            expect(t.fullText, `${lang}: no fullText`).toBeTruthy();
            expect(t.fullText.length, `${lang}: fullText too short to be real`)
                .toBeGreaterThan(200);
        }
    });

    it.each(Object.keys(DISCLAIMER_TRANSLATIONS))(
        '%s: the spoken fullText carries the RENDERED paragraphs',
        (lang) => {
            // The modal renders p1/p2/p3 but SPEAKS fullText -- two different
            // strings. If they diverge, what the applicant hears is not what
            // they read, and the doc's "same text on both surfaces" claim
            // silently stops being true.
            const t = DISCLAIMER_TRANSLATIONS[lang];
            for (const key of ['p1', 'p2', 'p3'] as const) {
                expect(
                    t.fullText.includes(t[key]),
                    `${lang}: ${key} is rendered on screen but is NOT inside `
                    + `fullText, so the spoken and written disclaimers differ.`,
                ).toBe(true);
            }
        },
    );

    it.each(INTRO_SCRIPT_LANGUAGES)(
        '%s: the modal renders the SHARED script, not its own copy',
        (lang) => {
            // REGISTER, settled by the maintainer 2026-08-19 (bd
            // polyglot-pdf-nsb4y): ONE SOURCE. What the modal renders and what
            // the model speaks both come from intro_script.json, so a reader
            // and a listener accept the SAME terms behind the same Agree
            // button. Before this, the modal said "we strongly advise"
            // (advice) while the audio said "you agree to review" (an
            // undertaking).
            //
            // This pins the WIRING -- that the rendered text IS the shared
            // script. The CONTENT of the undertaking is pinned per-language in
            // backend/tests/unit/test_intro_script.py, which anchors English
            // verbatim and guards translations with calibrated length floors.
            // Re-asserting an English phrase against translated text is the
            // bug that pass caught; do not reintroduce it here.
            render(
                <DisclaimerModal
                    isOpen
                    selectedLanguage={lang}
                    introParagraphs={renderIntroParagraphs(lang, 'I-90', 'I Agree')}
                    onListenAgain={() => {}}
                    onAgree={() => {}}
                />,
            );
            for (const paragraph of renderIntroParagraphs(lang, 'I-90', 'I Agree')) {
                expect(screen.getByText(paragraph)).toBeTruthy();
            }
        },
    );

    it('the English undertaking reaches the SCREEN, verbatim', () => {
        // English is the source language and is not translated, so the exact
        // clause is assertable -- and this asserts it against the RENDERED
        // DOM, not a constant: the whole bug was that a pinned constant said
        // one thing while the screen showed another.
        render(
            <DisclaimerModal
                isOpen
                selectedLanguage="English"
                introParagraphs={renderIntroParagraphs('English', 'I-90', 'I Agree')}
                onListenAgain={() => {}}
                onAgree={() => {}}
            />,
        );
        const body = document.body.textContent?.toLowerCase() ?? '';
        expect(body).toContain('agree to review the completed document');
        expect(body).toContain('certified professional');
    });

    it('DISCLAIMER_TRANSLATIONS is no longer rendered OR spoken', () => {
        // The retired constant (bd polyglot-pdf-nsb4y). It survives only as
        // the modal TITLE source and the p1/p2/p3 fallback for a caller that
        // passes no introParagraphs. If a future edit routes user-facing
        // disclaimer BODY text through it again, the two-register bug returns:
        // this constant carries "we strongly advise" (advice) while the
        // shipped script carries "you agree to review" (an undertaking).
        //
        // Pinned as a SET: every app-code consumer, enumerated. A new one
        // fails here rather than silently reintroducing the drift.
        const overlaySrc = [
            readFileSync(resolve(__dirname, '../../demo/VoiceOverlay.tsx'), 'utf-8'),
            readFileSync(resolve(__dirname, '../../demo/VoiceOverlayMobile.tsx'), 'utf-8'),
        ].join(String.fromCharCode(10));
        // Strip comments: the explanatory notes ABOUT the retirement mention
        // fullText by name, and must not count as consumers.
        const code = overlaySrc
            .replace(/\/\/.*/g, '')
            .replace(/\/\*[\s\S]*?\*\//g, '');
        expect(code).not.toContain('.fullText');
    });
});
