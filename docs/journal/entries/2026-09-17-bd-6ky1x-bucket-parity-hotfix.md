---
date: 2026-09-17
bead: polyglot-pdf-6ky1x
tags: [schema-editor, deploy, testing, hotfix]
surfaces: [schema-editor/vite-plugins/deployKitEndpoint.test.ts]
---

# The bucket-parity test follows the kit bucket into cloudbuild.yaml (dev was red)

dev's schema-editor suite had been red since #836 (bd `oqtm7`, the thin Cloud
Build wrappers): `deploy-all.sh` lost its bare `${FORM_KITS_BUCKET:-...}`
default because `cloudbuild.yaml` computes the bucket itself as
`$PROJECT_ID-form-kits`, but the "default bucket parity" test still listed the
script. The branch has no required checks, so the merge did not stop; the
break surfaced on #843's CI.

The list drops `deploy-all.sh`; a new case pins the bucket's new home: at
least two `$PROJECT_ID-form-kits` references in `cloudbuild.yaml`, no other
`*-form-kits` spelling besides the `--form-kits` CLI flag, and the plugin's
`DEFAULT_BUCKET` equal to `<.firebaserc demo project>-form-kits`. Mutations
red: a second spelling in `cloudbuild.yaml`; a drifted plugin default. The
first commit's spelling check was vacuous -- a shell heredoc had turned the
regex's `\b` into a literal backspace byte -- caught by a mutation that stayed
green; the second commit rewrote the two regex lines from a script file.
`setup-cloud-build.sh`'s own bare default stays `polyglot-pdf-7p5wn`'s.

Fresh-eyes (Sonnet): one gap -- the comment cited the wrong PR and bead for
the wrappers (fixed: #836 / `oqtm7`); it also asked that the one-spelling
strictness be stated as deliberate (done). Test-only; no outer review.

## Lessons

- **A quoted heredoc still halves backslashes; `\b` becomes a backspace.** The
  regex looked right in every grep because the terminal does not show 0x08.
  `od -c` did. Regex lines go through a script file, never a heredoc.
