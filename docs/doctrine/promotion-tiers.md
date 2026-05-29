# Promotion-tiers doctrine: feature -> dev -> main

*Last updated: <DATE>.*

How code promotes from a working branch to production.

## The tiers

```
feature/<id-suffix>-<slug>      one bead's work; where the agent commits
        |  PR (reviewed: Copilot + fresh-eyes, looped to clean)
        v
dev                             integration branch; auto-deploys to STAGING
        |  fast-forward / promotion (maintainer-driven)
        v
main                            production; auto-deploys to PROD
```

- **Feature branches** always branch off freshly-pulled `dev`. One bead = one
  branch = one PR.
- **`dev`** is the integration branch and the PR base. Merging to `dev` triggers
  the staging deploy, where changes are verified against a prod-like environment
  before promotion.
- **`main`** is production. Only fast-forward promotions from `dev` land on
  `main` -- never a direct commit. The maintainer drives `dev -> main`.

## The merge gate

The repo's GitHub ruleset sets **allow_auto_merge=false**, so a PR -- even a
green, reviewed, ready one -- cannot merge itself. The maintainer clicks merge.
This is the single human gate; it is why the review flow (review-flow.md) can run
fully autonomously up to the point of pinging the maintainer. Set this up via
`branch-protection-setup.md`.

## Environment detection

Use ONE canonical signal for "which environment am I in" (e.g. a single
`IS_STAGING` / `APP_ENV` variable read through one helper), not ad-hoc hostname
or env-string checks scattered across the code. If the topology grows, migrate
the one helper; call sites keep working.

## Staging specifics

_(Document your staging URL, any basic-auth, and the env-var differences between
feature/staging/prod here. Keep secrets out of the doc -- reference the names,
not the values.)_
