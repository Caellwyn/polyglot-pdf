/**
 * THE VOICE-PATH EXIT INVARIANT (bd polyglot-pdf-xtj97, criterion 3).
 *
 * A field the voice session is sitting on must ALWAYS have at least one exit:
 * the model can confirm it, skip it, or clear it. If all three refuse, the form
 * can never be COMPLETED -- isSectionValid (schemaFormState.ts) fails forever on
 * a required field that is blank and not skipped, and computeNextField's
 * Priority-2 arm hands the field straight back. The backend compounds it by
 * marking BOTH the confirm and skip refusals NON-RETRYABLE
 * (callback_handler.py), so the model is handed a field it cannot answer,
 * cannot skip, cannot clear, and is told not to try again.
 *
 * PRECISELY: the session is not frozen. `switch_to_field` pins another field,
 * and resolveLivePin (navigation.ts) returns that pin ahead of both priority
 * loops, so the model can move AROUND the bad field and keep working. What it
 * can never do is finish: the pin resolves, Priority 2 re-offers the field, and
 * the completion gate stays shut. Stranded-forever, not stuck-on-this-turn --
 * which is worse, because it surfaces at the END of a long session.
 *
 * WHY THIS IS A MATRIX AND NOT ONE CASE. The deadlock bd polyglot-pdf-5ovod
 * nearly shipped was not caused by any single guard being wrong. Each of the
 * three guards was individually correct and defensible:
 *
 *   - confirm refuses whitespace   (whitespace is not an answer)
 *   - skip refuses a filled field  (do not discard a real answer)
 *   - clear refuses '' on required (required fields need a value)
 *
 * The bug lived in their INTERSECTION: for one value shape -- a required field
 * holding "   " -- all three fired at once. Tightening the confirm gate closed
 * the last door, and nothing was watching the whole set. A test for the
 * whitespace case alone would not have caught it either, because the whitespace
 * case only became lethal once a DIFFERENT predicate moved.
 *
 * WHY THIS DRIVES THE REAL HANDLERS. The obvious way to write this sweep is to
 * re-type the three predicates as local helpers and assert over those. That
 * version passes forever: it tests the test's copy of the rules, so production
 * can drift out from under it and the invariant silently becomes decorative --
 * which is precisely how the original deadlock survived its own bead's tests
 * (bd 5ovod's escapability test called markFieldSkipped DIRECTLY, one layer
 * BELOW handleSkipFieldRequest's guard, so it could not see the guard at all).
 * So confirm and skip here fire real `confirm_field` / `skip_field` messages at
 * a real WebFormConnection and read the acks it sends back.
 *
 * The CLEAR arm is the one exception, and deliberately so: clearing goes
 * through validateField, a pure function, so it is called directly rather than
 * through the socket. It is a real call into shipped code, not a mirror.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { WebFormConnection } from './webFormConnection'
import type { FormSchema } from './schema-forms/types/schema'
import { validateField } from './schema-forms/utils/validation'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3
  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((e: any) => void) | null = null
  onerror: ((e: any) => void) | null = null
  onclose: ((e: any) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    queueMicrotask(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.()
    })
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })
}

const FIELD_ID = 'p1_uscis_number'

function schemaWith(required: boolean): FormSchema {
  return {
    source: 'web',
    form_metadata: { form_number: 'TEST-1', version: '1' },
    fields: [
      {
        id: FIELD_ID,
        name: 'USCIS Number',
        spoken_name: 'USCIS Number',
        type: 'text',
        validation: { required },
      },
    ],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: [FIELD_ID] }],
  } as unknown as FormSchema
}

function lastWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

function sentMessages(ws: MockWebSocket): any[] {
  return ws.send.mock.calls
    .map((c: any[]) => c[0])
    .filter((arg: any) => typeof arg === 'string')
    .map((s: string) => JSON.parse(s))
}

/** Stand up a real connection holding `value` in the one field. */
async function connectedWith(value: unknown, required: boolean): Promise<MockWebSocket> {
  const conn = new WebFormConnection(schemaWith(required))
  await conn.connect('wss://example/ws/fill')
  ;(conn as any).state.fieldValues[FIELD_ID] = { value }
  const ws = lastWs()
  ws.send.mockClear()
  return ws
}

/** EXIT 1 -- fire a real confirm_field and report whether it was REFUSED. */
async function confirmRefuses(value: unknown, required: boolean): Promise<boolean> {
  const ws = await connectedWith(value, required)
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'confirm_field', field_id: FIELD_ID, request_id: 'req-confirm',
    }),
  })
  await Promise.resolve()
  const ack = sentMessages(ws).filter(m => m.type === 'confirm_field_response')[0]
  // NO ACK COUNTS AS REFUSED, deliberately. The model got nothing back, so from
  // the session's point of view that exit did not open -- which is the deadlock
  // shape, not an escape.
  //
  // This does NOT hide a crashing handler behind a plausible-looking "refusal":
  // verified by making handleSkipFieldRequest throw, which reddens the sweep
  // loudly rather than passing. That is the right direction -- a handler that
  // throws HAS removed an exit, so a deadlock report is the honest reading.
  return ack ? ack.recorded !== true : true
}

/** EXIT 2 -- fire a real skip_field and report whether it was REFUSED. */
async function skipRefuses(value: unknown, required: boolean): Promise<boolean> {
  const ws = await connectedWith(value, required)
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'skip_field', field_id: FIELD_ID, request_id: 'req-skip',
    }),
  })
  await Promise.resolve()
  const ack = sentMessages(ws).filter(m => m.type === 'skip_field_response')[0]
  return ack ? ack.recorded !== true : true
}

/**
 * EXIT 3 -- clearing to ''. Calls the REAL validateField (a pure function, so
 * no socket needed): a non-null error is the rejection that blocks the clear.
 */
function clearRefuses(required: boolean): boolean {
  const field = schemaWith(required).fields[0]
  return validateField(field as any, '') !== null
}

/** Every stored value shape a field can hold when the model acts on it. */
const VALUE_SHAPES: Array<{ label: string; value: unknown }> = [
  { label: 'null', value: null },
  { label: 'undefined', value: undefined },
  { label: "empty string ''", value: '' },
  { label: 'whitespace "   "', value: '   ' },
  { label: 'tab/newline', value: '\t\n' },
  { label: 'a real answer "Maria"', value: 'Maria' },
  { label: 'the string "0"', value: '0' },
  { label: 'empty array []', value: [] },
  { label: "array ['White']", value: ['White'] },
  { label: 'boolean false', value: false },
  { label: 'number 0', value: 0 },
]

describe('the voice path always has an exit (bd polyglot-pdf-xtj97)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error -- override global WebSocket with the mock for the test
    global.WebSocket = MockWebSocket
    const store: Record<string, string> = {}
    global.sessionStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: () => null,
      length: 0,
    } as unknown as Storage
  })

  for (const required of [true, false]) {
    for (const shape of VALUE_SHAPES) {
      it(`${required ? 'required' : 'optional'} field holding ${shape.label} is escapable`, async () => {
        const refusals = {
          confirm: await confirmRefuses(shape.value, required),
          skip: await skipRefuses(shape.value, required),
          clear: clearRefuses(required),
        }
        const openExits = Object.entries(refusals)
          .filter(([, refused]) => !refused)
          .map(([name]) => name)

        expect(
          openExits,
          `DEADLOCK: a ${required ? 'required' : 'optional'} field holding ` +
            `${shape.label} refuses confirm AND skip AND clear, so the form can ` +
            `never be COMPLETED -- the model can switch away from it, but the ` +
            `completion gate stays shut forever and Priority 2 keeps handing ` +
            `the field back. The backend marks the confirm and skip refusals ` +
            `non-retryable, so it is told to stop trying. One exit must stay open.`,
        ).not.toEqual([])
      })
    }
  }

  it('the shape that deadlocked -- required + whitespace -- escapes by SKIP specifically', async () => {
    // The regression this bead was filed for. Named separately from the sweep
    // so that narrowing VALUE_SHAPES cannot retire the case silently, and so a
    // failure says WHICH exit was supposed to carry it.
    expect(await confirmRefuses('   ', true), 'confirm must refuse whitespace').toBe(true)
    expect(clearRefuses(true), "clearing a required field to '' must refuse").toBe(true)
    expect(
      await skipRefuses('   ', true),
      'SKIP is the only remaining exit for a required whitespace field; if it ' +
        'refuses too the session deadlocks -- this is the bug bd 5ovod nearly shipped',
    ).toBe(false)
  })

  it('a real answer still BLOCKS the skip -- the invariant is not "make everything permissive"', async () => {
    // The other side of the invariant. It must not be satisfiable by opening
    // every gate: skip must keep refusing a real answer, or the model could
    // silently discard what the user said.
    expect(await confirmRefuses('Maria', true)).toBe(false)
    expect(await skipRefuses('Maria', true), 'skip must never discard a real answer').toBe(true)
  })
})
