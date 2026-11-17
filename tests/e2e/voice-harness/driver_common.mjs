/*
 * Shared steps for the voice-harness Playwright drivers (bd polyglot-pdf-tcemw).
 * ASCII-only (repo rule).
 */

/**
 * Accept the disclaimer AND wait for the dev inject hook, in whichever order
 * the app presents them (bd polyglot-pdf-s1iex.7).
 *
 * The order is flag-dependent:
 *  - intro clip OFF (today): the app connects -- and installs
 *    window.__VFF_TEST_INJECT -- before Agree is clicked;
 *  - intro clip ON: no session, and so no hook, exists until Agree.
 *
 * So neither "wait for the hook, then click" nor "click if already visible,
 * then wait" is safe: the first hangs under the clip, and the second silently
 * skips Agree whenever the modal is slower than the visibility probe, leaving
 * the session parked on the disclaimer turn. Poll for both until Agree has
 * been clicked AND the hook exists.
 *
 * `pattern` is the Agree button's label regex (match the TRANSLATED label for
 * a non-English session).
 */
export async function agreeAndWaitForHook(page, pattern, log, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  let agreed = false;
  while (Date.now() < deadline) {
    if (!agreed) {
      const button = page.getByRole('button', { name: pattern }).first();
      try {
        if (await button.isVisible()) {
          await button.click();
          agreed = true;
          log('clicked disclaimer agree');
        }
      } catch {
        // Not present yet (or re-rendered mid-click): poll again.
      }
    }
    const hook = await page.evaluate(
      () => typeof window.__VFF_TEST_INJECT === 'object' && window.__VFF_TEST_INJECT !== null);
    if (agreed && hook) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`disclaimer agree / inject hook not reached in ${timeoutMs}ms`);
}
