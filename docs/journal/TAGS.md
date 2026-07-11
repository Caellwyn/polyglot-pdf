# Journal entry tags -- canonical vocabulary

*Last updated: 2026-07-10.*

Tags used in the YAML frontmatter of [`entries/*.md`](entries/). **Adding a tag
is a deliberate edit to THIS file** -- never invent a tag ad-hoc in an entry.
Renaming a tag means editing every entry that uses it (avoid).

## Rules

1. Each entry MUST have 1-5 tags, all appearing verbatim in the list below.
2. Lowercase-kebab-case or lowercase-snake-case.
3. Adding a tag is its own atomic commit editing only this file.

## All tags (flat -- the source of truth)

- conventions
- performance
- review
- security
- testing
- refactor
- hotfix
- postmortem
- harness
- doctrine
- extractor
- schema-editor

## Usage example

```markdown
---
date: 2026-01-15
bead: myproject-ab12
title: "Short description of what shipped"
sprint: 3
tags: [testing, refactor]
---
```
