---
date: 2026-08-27
bead: polyglot-pdf-dft1
tags: [client-links, resume, pdf, security, tts, i18n, testing]
---

# The client's saved PDF is the save file

bd `polyglot-pdf-dft1`. A pilot blocker, and the one that mattered most: today
a client who steps away for an hour loses **every answer**. `schemaFormState`
discards state after 60 minutes and re-initialises with `fieldValues: {}`. That
is live behavior, independent of any spend cap.

The maintainer's design: piggyback on the save the client already does.
*"We already have a 'save' function that saves the form as a pdf ... We can
track the link ids used, and the form session id in pdf metadata to allow the
resume."*

## Why it works: the file already holds both halves

Measured with PyMuPDF before building anything:

- custom JSON in PDF metadata round-trips byte-identical
- filled field VALUES read back out of a saved document

So the client's own file is a complete save file -- their answers in the form
fields, their identity in the metadata -- with **no server storage**, which is
what keeps the stateless-architecture rule intact.

## The upload is attacker-controlled, and the maintainer said so first

*"a thorough check that it matches the form they were assigned. I'd want a byte
match on everything except the field data to help prevent bad actors from using
this for prompt injection or some other attack."*

**A literal byte match cannot work**, measured before building: filling the same
kit twice with identical values produces DIFFERENT bytes -- same length,
different sha256 -- because PDFs embed timestamps and object ids. Implemented
literally it would refuse every legitimate resume.

The structure digest is what "everything except the field data" means in
practice: page count and geometry, the complete widget inventory (name, type,
rounded rect, sorted so file order cannot matter), and each page's STATIC text.
Refused, each pinned against the real W-7 kit: a different form, injected page
text, an added widget, a moved widget, an added page, a removed page, anything
unreadable. A missing reference form FAILS CLOSED.

### The near-miss worth remembering

The first digest **passed all eight attack tests and rejected every legitimate
resume.** A filled field renders its value into the page's text layer, so
hashing page text hashed the client's own answers -- the one thing the digest
must ignore.

**A security check that refuses everything passes every attack test perfectly.**
Only the happy-path test caught it, which is why it was written alongside them.
The fix hashes static text with words inside widget rects excluded; injection is
still caught because text added where the form has no field lands outside every
rect, and text hidden UNDER a widget is covered from the other side by the
widget inventory pinning every rect.

## The paid-TTS conflict, and the maintainer's call

Wiring the spoken nudge surfaced a real design problem: both `/api/tts/*` routes
declare `require_paid_client_work`, which REDEEMS the link. So the spoken "save
your form now" would have

- answered the budget-exhausted client with silence -- exactly who needs it, and
- BURNED a live client's link to deliver a warning we chose to give.

Maintainer: our own safety messages must not count against a client's budget.
`POST /api/tts/notice` is `require_auth` instead, and follows the contract
`/api/tts/intro` already set: **the caller sends a KEY, never text.** That is
what stops a free route from becoming an open text-to-speech service for anyone
holding a link.

## Translations derived, not written twice

The Python notice table is GENERATED from `resumeStrings.ts` -- the text a
client SEES -- and a parity test re-derives it to prove they still agree. A
client hearing one thing while the screen says another is worse than either
alone.

**The parity test found a real bug on its first run:** Chinese had a leading
space the printed text did not. The generator wrapped long lines by splitting on
SPACES, fine for spaced languages and silently corrupting Chinese, Japanese or
Thai where the sentence is one "word". Fixed in the generator, so the next
language added cannot hit it.

## Ten well-tested modules, zero mounted

Before the wiring commit, this feature had ten modules with passing unit tests
and **not one of them reachable by a client.** Every test green; nothing
rendered.

That is the same shape that broke the client path five times in bd `ugm6`, and
unit tests cannot see it by construction -- they test the piece, not whether
anything calls it. The `resumeWiring` guard is derived from the shipped source
and mutation-verified the honest way: deleting the mount reddens 2 wiring tests
while all 23 unit tests stay GREEN.

It also pins the ORDERING (the resume choice must precede the disclaimer, so a
resuming client agrees for the session they are about to work in) and the
enumerated set (download and print stamped, the preview deliberately not).

## Three environment traps, all found by tests failing

Worth recording because each looked like a test problem and two were product
problems:

1. **No auto-cleanup** for React Testing Library in this project -- an unmounted
   render stays in the document and `document.querySelector` finds the stale
   one. Six tests failed that way.
2. **`File.arrayBuffer()` is undefined** in this jsdom. Not just a test gap: a
   client recovering their work is exactly the person on an older phone, so the
   component now falls back to `FileReader`.
3. **`URL.createObjectURL` is undefined** there too, so creating the blob URL
   inside `speak()` threw and the silent-failure catch HID it -- a test that
   looked like it passed while playing nothing. `play()` now takes the Blob.

## tsc caught a runtime bug the tests missed

`fieldValues` holds `FieldValue` OBJECTS (value, confirmed, confirmedAt,
confirmationMethod, lastModified) and `applyResume` was merging bare strings --
which would have corrupted every reader of `.value` or `.confirmed` at runtime,
not merely failed a type check. The tests passed because they asserted on what
the merge RETURNED rather than on its SHAPE.

Restored answers are marked `manual_edit`, not `ai_voice`: they came from the
client's own file, not from something the assistant heard this session.

## What is NOT done

- **`polyglot-pdf-1uyof`** (carry `form_session_id` across a replacement link)
  depends on this and is still open. The stamp carries the jti list already; the
  aggregation work is separate.
- **`polyglot-pdf-cke6v`** (a spend-exhausted client sees a generic "reconnect
  failed" modal) can now reuse the ending notice rather than building a second
  modal pipeline.
- The resume flow has not been exercised against a live browser end to end. The
  route, the verifier, the merge and the mounts are each tested, and the wiring
  guard proves they are connected, but nobody has clicked through it.

## The review found the feature did not work

Six blocking findings, every structural claim verified independently before
fixing. The headline: **a real W-7 resume returned ZERO usable answers.**

- the route returned values keyed by PDF WIDGET NAME; `fieldValues` is keyed by
  SCHEMA FIELD ID, and **zero of the W-7's 53 ids equal their pdf_field_name**
- `section.fields` is `string[]` of ids, not objects -- the index built on all
  three shipped kits was EMPTY
- an untouched W-7 already carries 21 `'Off'` checkbox widgets, which would
  have been written as confirmed answers on a form nobody filled in
- the mount used `form_metadata.form_number` (`"W-7"`); the kit is `"w7"`, so
  every resume 404'd
- neither new route was given an auth token, so both 401 in any deployed
  environment -- working only under the local `VFF_DISABLE_AUTH` bypass
- the nudge's Save button dispatched an event NOTHING listened for, silencing
  both nudges permanently while downloading nothing

### Why the tests missed all of it

Every fixture I wrote invented a shape no shipped kit produces. The route test
filled a widget BY NAME and asserted that SAME STRING came back -- so it passed
*precisely because* it conflated the two namespaces the bug conflates. Three of
those tests FAILED once the route was fixed: they were pinning the bug.

**And the mount guard I was pleased with caught none of it.** It proved
components were RENDERED, not that they were rendered CORRECTLY WIRED. A
wiring guard that checks presence is one layer removed from a wiring guard that
checks the values being passed.

The generalisable rule: **a fixture you invented cannot falsify an assumption
you also invented.** Every fix here is now pinned by a test derived from the
REAL shipped kits.

### Dead code removed rather than left to mislead

`resumeFromPdf.ts` -- the browser-side PDF reader -- had no production
importer. The design moved mid-build: the SERVER verifies uploads, so a
client-side reader became redundant. Its Python/TypeScript parity guard was
therefore defending nothing while implying protection. Both removed, with the
guard's real subject (`_is_safe_session_id`) still exercised where it is
actually used.

## Round two: a fix I reported that never landed, and a probe that lied

The re-review returned NO-GAPS, and was still worth reading closely.

**I claimed a fix that did not exist.** The section-shape bug was fixed in the
ROUTE and I reported it fixed everywhere. `applyResume.firstIncompleteSection`
still walked `section.fields` as objects, behind an `as unknown as` cast that
hid the mismatch from tsc -- so it returned the fallback for every shipped kit,
and a client who saved at question 60 restarted at question 1.

**The seventh invented fixture was exactly where the review was pointed.**
`applyResume.test.ts` used `fields: [{ id }]`, and that fixture was the sole
reason the section-landing tests were green. It now loads the real W-7 schema.

### A probe can fabricate the bug it claims to find

Fixing radio restoration, my first probe "proved" radio answers were lost. The
proof was wrong. It called `widget.update()`, which silently reverts these XFA
checkboxes -- so I was measuring a failed SETUP and reporting a failed FEATURE.

Driving the real `/api/fill-pdf` route instead revealed the actual mechanism,
which neither the reviewer nor I had seen: **a checked box lives in `/AS` while
`/V` stays `"Off"`.** PyMuPDF therefore reports `field_value` as `"Off"` for a
box the client genuinely ticked. On the W-7 that silently emptied
`application_type`, `reason` and `sex` -- the form's core routing questions --
while the client's text came back and everything looked fine.

Two fixes: read the state from `/AS`, and map OPTION-level `pdf_field_name`
entries, because radio and checkbox_group map per option rather than at the top
level (6 of the W-7's 53 fields).

**The lesson, widened:** a fixture you invented cannot falsify an assumption you
also invented -- and a probe you wrote by hand can manufacture the very bug it
claims to find. The tests that now pin this drive the REAL fill route, so the
setup cannot be wrong in a way the assertion cannot see.

## Round three: the same mistake at a third altitude

I fixed the W-7 and broke the other two kits in a new way.

`pdf_on_value` exists on **21 of 21** W-7 option widgets and on **zero** of the
i-90's 75 and the f1040's 24. I keyed the option mapping on it, so radio and
checkbox answers restored perfectly on the kit I tested and were lost entirely
on the other two -- while emitting keys their schemas do not contain. The i-90
is `status: complete`, so a real client could reach it.

Not an invented fixture this time. A **real kit that happened to be the only
one where my assumption held.**

The fix reads the on-state from the WIDGET, exactly as the fill path derives it
(`get_button_on_state`), which is robust across kits because it reads what the
PDF actually says. Each option widget now also carries its parent field id
explicitly: the old code found the parent by searching for the first field
containing that option VALUE, and values are not unique -- 13 are shared across
fields on the i-90, so answers landed on the wrong field.

### The set, one more time

Fixing the unhandled-store-error finding, I patched the schema load and wrote
the test. **It failed** -- the reference-form load had the identical gap. I had
fixed the instance in front of me and not the set, which is scar #8 catching me
in miniature, inside a single function.

### Three rounds, one shape

| Round | The thing that was only true where I looked |
|---|---|
| 1 | a fixture I invented |
| 2 | a probe I wrote by hand, which fabricated the bug it "found" |
| 3 | a real kit that was the only one carrying the key I depended on |

Each time the tests were green and the feature was broken for a real client.
The durable lesson is not about PDFs: **evidence I constructed cannot falsify an
assumption I also constructed.** What broke the pattern each time was going to
the shipped artifacts -- the real kits, the real route -- and enumerating the
whole set rather than the instance.

## Round four: the fourth instance, and a bead I filed on a false premise

The resume route looked widgets up by EXACT key. The fill path falls back to
`endswith`, and its docstring says why: *XFA PDFs use full paths while our
schema might only have the bare leaf.*

The i-90's 114 direct mappings are **0 exact, 114 suffix-only**. So a client on
the only `status: complete` kit -- the one a real client actually receives --
resumed **12 of 110** answers, losing every text field: name, A-Number,
address, date of birth.

| Kit | Before | After |
|---|---|---|
| W-7 | 46/46 | 46/46 |
| i-90 | **12/110** | **107/107** |
| f1040 | 68/68 | 68/68 |

### I filed a P1 bead that was wrong

`polyglot-pdf-t4qo7` claimed the i-90's schema named 114 widgets ABSENT from
its own PDF, and that filling never printed them. Every part of that was false.
All 114 are present; the fill path writes them correctly. I had checked EXACT
matches only -- the identical mistake to the bug I was chasing -- and concluded
a gold-standard kit was broken. Closed as INVALID rather than fixed.

That is worse than the code bug: it would have sent the maintainer to
re-derive a kit that was fine.

### "Improved" is not "fixed"

Adding the fallback took the i-90 from 98 lost to 7. I could have shipped that.
The remaining 7 were the `/AS` read still being gated on an exact match, so it
was skipped before the fallback ran. Resolving the mapping FIRST, then reading
the appearance state, took it to zero.

### The test that would have caught it on day one

Fill EVERY field, save, resume, assert nothing lost and nothing changed, across
ALL THREE kits. Every earlier test filled ONE field on the one kit whose naming
happened to match exactly -- which is how this survived four review rounds.

The pattern completes: **round 1** an invented fixture, **round 2** a probe I
wrote that fabricated its own finding, **round 3** the one kit carrying the key
I depended on, **round 4** the one kit whose widget naming matched exactly. Four
different disguises for the same error -- generalising from the single case in
front of me -- and each time a green suite with the feature broken for a real
client.

