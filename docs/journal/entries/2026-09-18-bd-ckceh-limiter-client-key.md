---
date: 2026-09-18
bead: polyglot-pdf-ckceh
tags: [security-audit, backend, rate-limit, staging]
surfaces: [backend/utils/rate_limit.py, backend/tests/unit/test_rate_limit.py]
---

# The limiter's client key is the browser hop alone: Hosting's egress changes per request

The first staging deploy carrying the rate limiter (bd `o2fub`, #847) was
measured with bursts of 48 sign-up checks (a nonexistent address; the door
answers the uniform 404 either way, so the handler's own
`signup_check_refused` line counts how many calls reached it):

| burst | connecting addresses in the request log | handler runs | `rate_limited` lines |
|-------|-----------------------------------------|--------------|----------------------|
| direct at run.app, no forged header | 1 | 30 | 18 (`bucket=client budget=30`) |
| through the Hosting `/api/**` rewrite, no forged header | 48 distinct | 48 | 0 |
| through Hosting, a rotating forged `X-Forwarded-For` prefix | 45-48 distinct | 48 | 0 |

So the limiter works exactly as designed for a direct caller and never
fires for browser traffic: Hosting's proxy connects to Cloud Run from a
different egress address on every request, and both of `o2fub`'s keys
(`prev|last` for the client bucket, `last` for the connection bucket)
included that address, so every request opened a fresh bucket. No user was
ever refused (the failure was toward permissiveness), and the direct path
was protected throughout.

## What changed

The client bucket is keyed on the SECOND-TO-LAST hop alone (the last when
the chain has one hop, the socket peer when there is no chain): through
Hosting that is the browser's address as Hosting appended it, unforgeable
by the browser and stable while the egress rotates; on a direct call it is
whatever the caller put there, which the connection bucket (still keyed on
the unforgeable last hop) backstops at the shared rate, as before. The
refusal log line gains `hops=<count>` (the chain length, a number) so the
next staging burst shows which hop the key came from. New pin: a browser
hop with a rotating last hop is refused at the 4th call; the old pair key
reddens it (2 failed). The forged-prefix, rotating-forge and
one-abuser-behind-Hosting cases pass unchanged.

What this still assumes: that Hosting APPENDS the browser address. The
measurement could not see the chain (the app logs no hops), only that the
last hop rotates; if Hosting passed a client-supplied header through
without appending, the client key through Hosting would be forgeable and
the connection bucket -- rotating with the egress -- would not backstop it.
The REFUSAL is the evidence, the `hops` count only names the hop: a
hosted burst that IS refused at the 31st call, with `hops` of 2 or more on
that line, means the browser hop is real and stable. A hosted burst that is
never refused is consistent with both a verbatim passthrough (`hops=2`,
forgeable key) and no browser hop at all (`hops=1`); `hops=2` on its own
decides nothing.

## Verification

- `test_rate_limit.py` (14) and the PII guard: green; mutation (the pair
  key restored): 2 red.
- Full suite: SUITE_RESULT

REVIEW_RECORD

## Files

`backend/utils/rate_limit.py`, `backend/tests/unit/test_rate_limit.py`,
`docs/components/config-deployment.md`, `docs/standards/security-posture.md`.
