/**
 * THE one rule for "is this DOM element a member of this field's option group?"
 *
 * Extracted because hand-syncing it across modules failed TWICE in bd
 * polyglot-pdf-96um6, in the same dimension both times:
 *   - I added the MEMBERSHIP test to fieldManager and not to connection.ts.
 *   - I then added the TYPE FILTER to fieldManager and harness.js and not to
 *     connection.ts, silently dropping the value of any text field whose own
 *     name happens to be bracketed -- a regression against origin/dev that
 *     1444 green frontend tests did not see.
 * A comment above the second copy asserted parity that did not hold. Comments do
 * not keep two copies in step; one function does.
 *
 * tests/e2e/voice-harness/harness.js still carries a hand-written twin because
 * it is injected into a live page and cannot import a module. That twin is
 * pinned by fieldIdNameCollision.test.ts, which reads its source.
 *
 * WHY IT IS SHAPED THIS WAY. Ids and names share no namespace in HTML, so a
 * field's id can collide with ANOTHER field's group name. Two independent things
 * must both hold for the group path to be correct:
 *   TYPE       -- only a radio/checkbox can be a group member, so a text field
 *                 named `race[]` is never one.
 *   MEMBERSHIP -- the element asking must itself be among the inputs found, so a
 *                 standalone control whose id merely collides is never one.
 * Neither subsumes the other; both are load-bearing and separately tested.
 */

/** The inputs of `fieldId`'s option group, or [] if it has none. */
export function groupInputsFor(fieldId: string): HTMLInputElement[] {
	const bracketed = (
		Array.from(
			document.querySelectorAll(`input[name="${fieldId}[]"]`)
		) as HTMLInputElement[]
	).filter(el => el.type === 'checkbox' || el.type === 'radio')
	if (bracketed.length) return bracketed

	const plain = Array.from(
		document.querySelectorAll(`input[name="${fieldId}"]`)
	) as HTMLInputElement[]
	const radios = plain.filter(el => el.type === 'radio')
	return radios.length ? radios : []
}

/**
 * Whether `element` -- the thing an id lookup resolved to -- rules OUT the group
 * path for `fieldId`. True means "treat this as a single control".
 */
export function idResolvesToNonGroup(
	element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null,
	fieldId: string
): boolean {
	if (element === null) return false
	if (element instanceof HTMLInputElement) {
		if (element.type !== 'radio' && element.type !== 'checkbox') return true
		// A radio/checkbox can STILL be a standalone field whose id merely
		// collides with another group's name. The decisive test is membership.
		return !groupInputsFor(fieldId).includes(element)
	}
	return true
}
