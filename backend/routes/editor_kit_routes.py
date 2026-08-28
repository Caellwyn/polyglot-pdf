"""
Editor Kit Routes -- the token-gated read/write surface for the hosted schema
editor (bd polyglot-pdf-92qe.1).

The public /api/form-kits* routes (form_kit_routes.py) serve the VOICE app and
are manifest-gated: in GCS mode they never list or serve a draft kit. The hosted
schema-editor needs the opposite -- a contractor's job IS the drafts: see them,
edit their schemas, flip their status. So this is a separate surface that
enumerates the store directly (list_kit_files + per-kit metadata.json),
bypassing the complete-only manifest ON PURPOSE, and gated by PER-USER identity
instead of being public.

Two access tiers (the 2026-07-01 goal's contractor permission levels), now
carried by a person rather than a shared secret (bd polyglot-pdf-hn0jq):

  - editor: list/read kits incl. drafts, save schemas, flip status -- the
    "polish a provided collection" contractor.
  - author: everything editor can do; onboarding + hosted extraction routes
    (bd 92qe.3) additionally require this role.

Authentication is a Firebase ID token carrying the editor's OWN role claim --
see backend/services/editor_auth.py, which owns the whole mechanism. 401 for a
token that does not verify, 403 for a valid account with no editor claim (they
authenticated fine; they are simply not listed here). The former shared secrets
were REPLACED, not deprecated: the maintainer had no live subcontractors, so
this was a clean cutover rather than a coexistence path.

WHY PER-USER: with two shared secrets every editor was one principal to the
server. An audit could only ever say "an editor did it", two subcontractors
could not be told apart by the kit lock, and removing one person meant rotating
the token for everyone.

Status semantics: marking a kit `complete` is the publish gate the deploy keys
on, so THAT transition validates the schema against the canonical Pydantic
FormSchema -- a contractor cannot promote a structurally-broken schema. Draft
saves stay lenient (work-in-progress is allowed to be incomplete).
"""

import asyncio
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional

import anyio

from fastapi import (
    APIRouter, Body, Depends, File, Form, Header, HTTPException, Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import structlog

from backend.config import get_settings
from backend.models import conditional_vocabulary as vocab
from backend.models.form_models import FormSchema, FormSource
from backend.routes.form_kit_routes import _safe_kit_id
from backend.services.kit_gates import (
    is_safe_marker,
    # ONE definition of the default/sanitized (schema, pdf) filename pair,
    # beside the archive helper that is its main consumer. It was duplicated
    # byte-for-byte here after that move (fresh-eyes r1) -- two copies of one
    # rule is the shape CLAUDE.md scar #7 names.
    _resolve_meta_names,
    # Moved out of this module (bd polyglot-pdf-z6bk9): the client-tier firm
    # retire route needs it too, and routes importing routes would be
    # circular. Imported under its original private name so every call site
    # here is unchanged.
    _archive_published_revision,
)
from backend.adapters.text_ai_gemini import TextAIGemini
from backend.services.editor_text_ai import (
    EditorTextAIUnavailable,
    resolve_editor_text_ai,
)
from backend.services.option_translation import (
    TRANSLATE_RETRY_DELAYS,
    bake_label_translations,
    translation_coverage_summary,
)
from backend.services.publish_readiness import publish_readiness
from backend.services.schema_lint import (
    SEVERITY_ERROR, SEVERITY_WARNING, lint_schema,
)
from backend.services.schema_repair import (
    RepairError, alias_hit_count, repair as repair_schema,
)
from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47
from backend.services.widget_picker import unclaimed_button_widgets
from backend.services.editor_auth import (
    EditorActor,
    require_author_actor,
    require_editor_actor,
)
from backend.services.form_kits import (
    FormKitNotFound,
    FormKitStoreError,
    LocalFormKitStore,
    encode_marker,
    get_form_kit_store,
    sibling_marker,
)
from backend.utils.confirmation_logger import (
    ConfirmationCheckUnavailable,
    kit_has_confirmation_records,
    resolve_edition_marker,
)

_log = structlog.get_logger().bind(module="editor_kit_routes")

router = APIRouter(prefix="/api/editor", tags=["editor-kits"])

# extract_form.py's tri-state exit code for a stored-with-issues draft (bd
# polyglot-pdf-v96b, P5.3a). Mirrored here (the extractor runs as a subprocess,
# so the route cannot import the constant); extract_form.EXIT_ISSUES is the
# source of truth and a sync test pins the two equal.
_EXTRACT_EXIT_ISSUES = 3



async def require_editor_role(
    actor: Annotated[EditorActor, Depends(require_editor_actor)],
) -> EditorActor:
    """FastAPI dependency: the caller, AS A PERSON, with role editor|author.

    Was: a role string resolved from a shared X-Editor-Token, so every editor
    was one principal to the server. Now: a Firebase ID token resolved to an
    EditorActor carrying uid + email + role (bd polyglot-pdf-hn0jq).

    The NAME is unchanged so the ~26 Depends() sites did not have to churn; what
    changed is the type. Sites that only need the gate are unaffected; the ~10
    that use the value read `.role`. Author still strictly includes editor.

    `.label()` is used in LOG LINES ONLY -- no response carries a person yet.
    KitLockResponse.heldBy still returns a role string, deliberately: putting a
    person on the wire is child 2's job (bd polyglot-pdf-5tuas).
    """
    return actor


async def require_author_role(
    actor: Annotated[EditorActor, Depends(require_author_actor)],
) -> EditorActor:
    """Author-only gate (onboard/extract routes, bd 92qe.3). 403 for an editor."""
    return actor



class EditorSessionResponse(BaseModel):
    role: str


class StoreHandshakeBody(BaseModel):
    """One half of the same-folder handshake (bd polyglot-pdf-s2bf).

    In LOCAL mode the editor reads and writes the directory the human PICKED
    with the File System Access API, while the backend resolves the same kit id
    against its own FORM_KITS_LOCAL_ROOT. Those are the same folder in the
    normal flow, but nothing enforced it -- so pointing the editor at a copy
    elsewhere meant the server-side actions (repair, regenerate divisions,
    regenerate guidance) silently rewrote the OTHER copy while the editor
    re-read the picked one. Destructive, and invisible.

    The browser cannot read a filesystem path out of a directory handle (by
    design), so the two sides cannot compare paths. Instead the editor writes a
    nonce into the picked folder and asks the backend to read it back from its
    OWN root: if the backend sees the same nonce, both are looking at one
    directory. Proof by shared observation rather than by comparing names.
    """

    nonce: str


class StoreHandshakeResponse(BaseModel):
    # True when the backend read the SAME nonce from its own root.
    sameFolder: bool
    # The backend's root, for the error dialog. Local dev only, and it is a
    # path the operator already knows -- it is their own working copy.
    backendRoot: Optional[str] = None
    # Why the handshake failed, for the dialog. The backend returns exactly
    # three values: "not-a-local-store" (this deployment has no local root),
    # "mismatch" (nothing readable at the backend's root -- no marker, or
    # one it could not parse; the editor is pointed somewhere else),
    # or "stale" (the marker is there but carries an older nonce). NOT
    # "unwritable" -- that one is minted client-side when the editor cannot
    # WRITE its marker, and it returns before this route is ever called
    # (schema-editor/src/utils/formKitDirectory.ts).
    reason: Optional[str] = None


class ReadinessStamp(BaseModel):
    """A kit's recorded review progress (sprint-18 C4, bd polyglot-pdf-g687).

    Written into metadata.json at save/publish by publish_readiness -- the SAME
    function the editor strip mirrors and the publish gate refuses on -- so the
    catalogue card reports a stored answer instead of re-deriving its own.

    `verified` is False when the counts were computed WITHOUT a usable lint
    report: the numbers are then honest-but-unchecked and the card must render
    the verify hint, never a confident percentage. `schemaSha1` scopes the stamp
    to the schema it measured, FOR A CALLER THAT HOLDS THE SCHEMA and can
    compare. The catalogue listing does not hold one (not re-reading every kit
    is the point of the stamp), so it cannot detect an out-of-band edit today --
    bd polyglot-pdf-j8sr tracks re-stamping the routes that rewrite a schema.
    """

    reviewed: int
    toReview: int
    total: int
    errors: int
    percent: int
    ready: bool
    verified: bool
    schemaSha1: str
    stampedAt: Optional[str] = None


class EditorKitInfo(BaseModel):
    """One kit as the editor catalogue sees it -- mirrors the local editor's
    CatalogueEntry (schema-editor formKitDirectory.ts) minus the directory
    handle, so the hosted catalogue renders from the same shape."""

    id: str
    label: str
    description: Optional[str] = None
    status: str  # draft | submitted | complete | unpublished | unknown
    hasSchema: bool
    hasPdf: bool
    schemaFile: str
    pdfFile: str
    # Absent when the kit has never been saved since C4 shipped (or its stamp
    # is unreadable) -- the card then shows the verify hint, not a percentage.
    readiness: Optional[ReadinessStamp] = None
    # Who holds this kit for editing, if anyone (bd polyglot-pdf-hqztg). A ROLE,
    # not a person. The catalogue cannot show a lock it cannot see, so this
    # rides the listing rather than forcing a per-kit probe.
    #
    # heldBy stays a ROLE deliberately (bd polyglot-pdf-5tuas): the editor
    # catalogue compares it to the literal strings "author"/"editor" at EVERY
    # site that decides what the lock UI shows -- the badge, its tooltip, the
    # label, the is-this-mine check that gates the Release button, and the
    # take-back branches. Making heldBy a person makes all of them stop
    # matching. (Counted 7 on 2026-08-27; grep rather than trust this number.)
    # WHO holds it rides alongside in heldByLabel, additively, so the server
    # names a person without breaking a frontend bd polyglot-pdf-yswp3 owns.
    heldBy: Optional[str] = None
    # The person holding it (email, else uid). None for a lock written before
    # 5tuas, which stored only a role.
    heldByLabel: Optional[str] = None


class EditorKitListResponse(BaseModel):
    kits: list[EditorKitInfo]


class KitStatusBody(BaseModel):
    # "unpublished" retires a published revision: hidden from clients, but
    # write-locked so its bytes stay exactly what its confirmation records were
    # confirmed against (bd polyglot-pdf-6dz0). Omitting it here would 422 the
    # unpublish request before the route ever ran.
    # "submitted" omitted here would 422 the request before the route's own
    # transition rules ever ran -- the exact trap bd polyglot-pdf-6dz0 hit when
    # "unpublished" was added to the status set but not to this Literal.
    status: Literal["draft", "submitted", "complete", "unpublished"]
    # Cross-kit supersede: when publishing a kit while ANOTHER live kit serves
    # the same form, name it here and it is unpublished in the same request, so
    # the catalogue never shows two entries for one form. Same-kit republish
    # needs no flag -- one kit_id is one catalogue slot, so it replaces itself.
    replaces_kit_id: Optional[str] = None
    # The author's own revision marker, for a kit with NO government
    # edition_date (bd polyglot-pdf-xzw5). Required to publish such a kit --
    # otherwise its confirmation records fall back to an unreadable content
    # fingerprint. Ignored for a kit that HAS an edition_date (the government
    # marker wins and the client never shows the box).
    author_version: Optional[str] = None


class KitStatusResponse(BaseModel):
    """Result of a status flip (bd polyglot-pdf-783r).

    On a successful `complete`, the drift sweep ran: `retranslated` is the number
    of translation entries (option/spoken-name/section across languages) the sweep
    freshly BAKED (fanned into the schema) -- 0 when nothing had drifted -- and
    `translationModel` names the model, reported only when `retranslated > 0`
    (null for a to-draft flip, a fully-covered kit, or the edge case where a call
    ran but produced no usable translation -- the editor notice keys on the fanned
    count, not on whether an API call happened). A blocked completion never reaches
    this model: it raises an HTTPException whose detail carries the editor-facing
    "N of M" message."""

    ok: bool
    status: str
    retranslated: int = 0
    translationModel: Optional[str] = None
    # The kit retired by a cross-kit supersede, so the editor can confirm what
    # it actually took out of service rather than the author inferring it.
    supersededKitId: Optional[str] = None


class KitDeleteResponse(BaseModel):
    """The result of a guarded kit delete (bd polyglot-pdf-6x1j)."""

    ok: bool
    kitId: str
    # What was actually removed, counted from the store rather than assumed --
    # a delete that reports 0 is worth noticing.
    objectsRemoved: int


class KitLockResponse(BaseModel):
    """Who holds a kit for editing (bd polyglot-pdf-hqztg)."""

    ok: bool
    kitId: str
    # "editor" | "author" | null. A ROLE, not a person -- see the note on
    # EditorKitInfo.heldBy for why it stays one (bd polyglot-pdf-5tuas).
    heldBy: Optional[str] = None
    # The person holding it (email, else uid). None when nobody holds it, or
    # for a lock written before 5tuas.
    heldByLabel: Optional[str] = None
    # True when this call took the lock from someone else, so the UI can say so
    # rather than silently succeeding.
    preempted: bool = False


class KitLabelBody(BaseModel):
    """The new display label for a kit (bd 15ic). Whitespace-stripped server-side;
    an empty/blank label is a 422."""
    label: str


class LintFindingOut(BaseModel):
    """One lint finding as the editor's ValidationPanel renders it.

    Mirrors schema_lint.LintFinding.as_dict(): the raw finding fields plus the
    derived field_id (the field the panel focuses on click; null for a
    non-field-anchored finding like a dump widget-claim)."""

    severity: str  # ERROR | WARNING
    rule: str
    path: str
    message: str
    field_id: Optional[str] = None


class LintResponse(BaseModel):
    """Load-time lint report for a schema (bd h76m.11, P4.3).

    findings are in the linter's emission order; counts are the split the panel
    shows in its header. The frontend NEVER runs its own copy of these rules --
    this endpoint is the single Python implementation surfaced to the editor."""

    findings: list[LintFindingOut]
    errorCount: int
    warningCount: int


class RepairResponse(BaseModel):
    """One-click Repair-all result (bd polyglot-pdf-zgln, P5.3b).

    The repaired schema is stored server-side; this reports what changed. The
    `repairs` list + counts mirror the CLI's _bakeoff.authoring.repair block
    (same schema_repair.repair() call, so the output equals the CLI on the same
    input). errorCount/warningCount are the POST-repair lint counts the editor
    re-renders (they should drop toward zero)."""

    applied: int          # substantive repairs that succeeded
    dropped: int          # substantive repairs that dropped data (recorded ERROR)
    aliasHits: int        # invented-operator alias table hit count
    repairs: list[dict]   # the full repair report (verbatim from schema_repair)
    errorCount: int       # lint ERRORs remaining after repair
    warningCount: int     # lint WARNINGs remaining after repair


class TranslateOptionsResponse(BaseModel):
    """Standalone option-label translation bake (bd polyglot-pdf-2h9j).

    The kit's option label_translations were baked in place (the SAME
    backend.services.option_translation.bake_label_translations the extraction
    post-pass and the translate_option_labels.py CLI run) and stored. Idempotent:
    already-covered options are untouched, so re-running is cheap and fills any
    failed language's gap. errorCount/warningCount are the post-bake lint counts
    (baking only ADDS label_translations, so errors should not move; WARNINGs
    may rise by the persisted translation-flag count -- see `flags`)."""

    changed: bool                     # did the stored schema change at all
    model: str                        # the Gemini model that translated
    failedLanguages: list[str]        # languages whose batch call failed (re-run)
    languages: dict[str, dict]        # per-language {labels, missing, translated,
                                      # options_updated, failed, spoken_names,
                                      # names_missing, names_translated,
                                      # fields_updated} (bd tupu.1)
    # Verify/rectify gate flags from THIS bake (bd polyglot-pdf-9djc):
    # LintFinding-shaped dicts (severity=WARNING, rule=translation-*, path,
    # message, field_id). Also persisted into the stored schema's
    # _bakeoff.authoring.option_translation slot, where lint re-emits them --
    # so the ValidationPanel shows them on every later lint pass too.
    flags: list[dict] = []
    errorCount: int                   # lint ERRORs after the bake
    warningCount: int                 # lint WARNINGs after the bake


class DeriveDivisionsResponse(BaseModel):
    """Regenerate-divisions result (bd polyglot-pdf-6cfu.3).

    The kit's parts/sections were recomputed deterministically from its PDF
    (scripts/authoring/derive_sections.py -- the same pass extraction runs at
    step 3e) and stored; every field's section_id was re-filed. This reports
    the derivation summary plus the post-derivation lint counts the editor
    re-renders (the to-review-pending rule keys the review gate)."""

    strategy: str                     # name-convention | printed-heading | page-fallback
    parts: int                        # derived part count
    sections: int                     # derived section count
    toReviewSectionIds: list[str]     # sec_to_review* sections holding strays
    toReviewFieldIds: list[str]       # the fields a human must re-file
    notes: list[str]                  # derivation notes (cap splits, strays)
    errorCount: int                   # lint ERRORs after derivation
    warningCount: int                 # lint WARNINGs after derivation


class RegenerateGuidanceBody(BaseModel):
    """Optional scope for a guidance regeneration (bd polyglot-pdf-cpiw).

    `fieldIds` limits the rewrite to those fields -- the natural call from the
    staleness banner, which already knows exactly which fields drifted. Omitted
    (or empty) rewrites every askable field."""

    fieldIds: list[str] = []


class RegenerateGuidanceResponse(BaseModel):
    """Re-authored field guidance result (bd polyglot-pdf-cpiw).

    The staleness gate (bd anim) tells a reviewer that a field's guidance may
    no longer match what the assistant says, and offers two ways out:
    acknowledge it still reads correctly (free), or RE-AUTHOR it (costly).
    Only the free half existed -- this reports the costly half, so an editor
    does not have to hand-write guidance out of the instruction booklet."""

    regenerated: list[str]      # field ids whose guidance was rewritten
    skipped: list[str]          # requested ids with no proposal from the model
    model: str                  # which model produced it (recorded in provenance)
    booklet: Optional[str]      # the instructions PDF used, if any
    errorCount: int             # lint ERRORs after the rewrite
    warningCount: int           # lint WARNINGs after the rewrite


class UnclaimedWidget(BaseModel):
    """One PDF button widget the schema does not yet claim (bd nivy, P5.3c)."""

    name: str                        # the widget's PDF field name
    type: Optional[str] = None       # checkbox | radio
    on_value: Optional[str] = None   # the widget's non-Off state (-> option.pdf_on_value)
    tooltip: Optional[str] = None    # the /TU tooltip, a suggested label
    page: Optional[int] = None       # 0-indexed page (for the author's orientation)
    # True when this is one kid of a SHARED-name group (one dump name, >1 kid):
    # the option gets pdf_on_value + the FIELD carries pdf_field_name=name. False
    # for a distinct-name widget: the option carries pdf_field_name=name. Putting
    # the shared name on every option's pdf_field_name would trip the widget-claim
    # lint rule (bd nivy fresh-eyes / Opus fallback).
    shared_name: bool = False


class UnclaimedWidgetsResponse(BaseModel):
    """The kit's unclaimed button widgets for the "Add from PDF widgets" picker.

    Empty when the kit has no persisted AcroForm dump (pre-v96b kits) -- the
    picker then simply shows nothing to add."""

    widgets: list[UnclaimedWidget]


# A kit's lifecycle status (bd polyglot-pdf-6dz0).
#   draft       -- work in progress. Editable, invisible to the voice app.
#   complete    -- published. Write-locked, served to clients.
#   unpublished -- SUPERSEDED. Invisible like a draft, write-locked like
#                  complete. A retired revision's bytes are what its
#                  confirmation records were confirmed against (bd
#                  polyglot-pdf-w3zw), so it must never become editable again;
#                  it returns to complete only through the full publish gate.
#   submitted   -- FINISHED BY AN EDITOR, awaiting an author's review. Not
#                  deployable (deploy gates on "complete"), and WRITE-LOCKED:
#                  if an editor could keep editing after submitting, the author
#                  would review one thing and approve another. An editor
#                  reopens it deliberately via Revert to draft; an author
#                  publishes it (bd polyglot-pdf-hqztg -- editors are
#                  subcontractors, so releasing is the accountable party's act).
_KIT_STATUSES = ("draft", "submitted", "complete", "unpublished")

# Statuses whose schema may NOT be rewritten. The distinction that matters is
# write-locked vs editable, NOT "is it complete" -- every write gate asks this
# rather than comparing to "complete" directly, so adding a fourth status
# cannot silently reopen a lock (the two-value checks were the trap: an
# unpublished kit coerced to "unknown" and fell through every one of them).
_WRITE_LOCKED_STATUSES = ("submitted", "complete", "unpublished")

# Statuses meaning THIS KIT HAS BEEN SERVED TO CLIENTS. Deliberately NOT the
# same tuple as the write-lock, though they overlap: write-locked answers "may
# its bytes change?", while this answers "do confirmation records name it?".
# `submitted` is write-locked but was NEVER live -- reusing the write-lock
# tuple as a proxy made a submitted kit look published, so an author fixing a
# typo in its version was refused with a message about confirmation records
# that do not exist (Opus fresh-eyes round 4, reproduced). That is the exact
# bug bd polyglot-pdf-xzw5 fixed for drafts, reintroduced one status over by
# sharing a constant between two different questions.
_PUBLISHED_STATUSES = ("complete", "unpublished")


# --- the editing lock (bd polyglot-pdf-hqztg) --------------------------------
#
# ROLE-SCOPED, not user-scoped, and that is a known limitation rather than a
# design preference: the editor API authenticates with two SHARED tokens, so
# the server can record "an editor holds this" but never WHICH editor. Two
# subcontractors sharing one token still collide with each other exactly as
# they do today -- no better, no worse. bd polyglot-pdf-ijntk adds per-user
# identity and re-scopes this lock to a person.
#
# The rule the maintainer asked for: an AUTHOR can always take a lock back
# from an editor, and never the reverse. Preemption also IS the stale-lock
# release -- there is no timer, because a clock that steals a lock from
# someone actively working is worse than a human deciding to take it.
_LOCK_KEY = "editing_lock"


def _lock_after_transition(
    meta: Optional[dict], current: str, target: str, actor: EditorActor
) -> Optional[dict]:
    """The `editing_lock` value a kit should carry AFTER a status transition.

    A transition normally ends the editing turn -- handed up for review, handed
    back for changes, or published and write-locked -- so the lock is released
    and the next person can take it. Keeping it bricked the send-back flow: the
    editor 409'd on every action with no control to self-rescue (round 8).

    THE EXCEPTION: reopening a LIVE kit (`complete|unpublished -> draft`) does
    not end an editing turn, it BEGINS one. The author clicks "Revert to draft
    to edit it" precisely in order to edit, so dropping their lock there let an
    editor take it and write mid-edit -- a lost-update window against the
    accountable party the lock exists to protect (round 9, reproduced).

    The SOURCE is what separates the two, not the target: `submitted -> draft`
    is also a `-> draft`, but it is the send-back, which hands the kit to the
    editor and must release. Keying on the target alone recreated the round-8
    lockout -- caught because that round's test still asserted the send-back
    releases. The holder also keeps it only when THEY are acting; anyone
    else's stale lock is cleared regardless.
    """
    holder = _lock_holder(meta)
    if holder is None:
        return None
    reopening_a_live_kit = (
        target == "draft" and current in _PUBLISHED_STATUSES
    )
    if not reopening_a_live_kit:
        return None
    # "THEY are acting" is a PERSON test now, not a role test (bd 5tuas).
    # Role comparison had author Dana reopening a kit author Josh holds KEEP
    # HIS LOCK AS HERS -- indistinguishable to the old code, a silent
    # takeover once uids exist.
    holder_uid = _lock_holder_uid(meta)
    if holder_uid:
        if holder_uid != actor.uid:
            return None
    elif holder != actor.role:
        # A legacy lock has no uid: fall back to the role test rather than
        # dropping a lock we cannot attribute.
        return None
    # Return the lock UNCHANGED. Rebuilding it as {"role": holder} stripped
    # the uid and label, downgrading a person-scoped lock to the legacy
    # shape -- which falls back to the permissive same-role rule, so
    # reopening your own kit would quietly reopen it to everyone else.
    existing = (meta or {}).get(_LOCK_KEY)
    if isinstance(existing, dict):
        return dict(existing)
    return {"role": holder}


def _refuse_if_metadata_unreadable(
    meta: Optional[dict], files: set[str], kit_id: str, action: str
) -> None:
    """Refuse a read-merge-write when metadata.json is present but UNPARSEABLE.

    load_metadata degrades a parse failure to None (documented on the store
    ABC), so `meta is None` means EITHER "no metadata yet" OR "metadata exists
    and is corrupt". Merging into `{}` and writing is correct for the first and
    catastrophic for the second: it REPLACES the file, taking `status` with it
    -- and deploy-all.sh greps for `"status": "complete"`, so a live form
    silently drops out of the manifest and stops being served (Opus fresh-eyes
    round 5, reproduced: a take-lock returned 200 while leaving metadata.json
    as exactly {"editing_lock": {...}}).

    The filename set disambiguates, which is why _load_meta_or_404 returns it.
    _stamp_readiness already does this; this is the same rule, shared rather
    than copied a third time.
    """
    if meta is not None or _METADATA_FILE not in files:
        return
    _log.warning("editor_metadata_unreadable_write_refused",
                 kit_id=kit_id, action=action)
    raise HTTPException(
        status_code=409,
        detail=(
            f"This form's metadata.json cannot be read, so {action} would "
            f"overwrite it and lose the form's status. Fix the file first."
        ),
    )


def _lock_holder(meta: Optional[dict]) -> Optional[str]:
    """The ROLE currently holding this kit, or None.

    Still a role, because `heldBy` on the wire is still a role -- every site
    in RemoteCatalogue.tsx that decides what the lock UI shows compares it to
    the literal strings "author"/"editor", including the is-this-mine check
    that gates the Release button. Person identity rides alongside in
    `_lock_holder_uid`, additively, so this bead does not reach into the
    frontend that bd polyglot-pdf-yswp3 owns.
    """
    lock = (meta or {}).get(_LOCK_KEY)
    holder = lock.get("role") if isinstance(lock, dict) else None
    return holder if holder in ("editor", "author") else None


def _lock_holder_uid(meta: Optional[dict]) -> Optional[str]:
    """WHO holds this kit, as a stable uid -- the person-scoping (bd 5tuas).

    None for a lock written before this bead: those store only a role. A
    holder we cannot identify must not be treated as "somebody else", or an
    editor would be permanently locked out of a kit nobody is actually
    editing -- so same-role contention falls back to the old ALLOW.
    """
    lock = (meta or {}).get(_LOCK_KEY)
    uid = lock.get("uid") if isinstance(lock, dict) else None
    return uid if isinstance(uid, str) and uid else None


def _lock_holder_label(meta: Optional[dict]) -> Optional[str]:
    """A human-readable name for the holder, for display only."""
    lock = (meta or {}).get(_LOCK_KEY)
    if not isinstance(lock, dict):
        return None
    # "label" is read as a FALLBACK for any lock written between this bead's
    # first commit and the rename below -- none should exist outside a dev
    # tree, but reading both costs nothing and stranding a holder costs a
    # person their kit.
    label = lock.get("holder_label") or lock.get("label")
    return label if isinstance(label, str) and label else None


def _lock_refusal(holder: str, actor: EditorActor,
                  holder_uid: Optional[str] = None,
                  holder_label: Optional[str] = None) -> Optional[str]:
    """Why `actor` may not take a kit held by `holder` -- None when it may.

    TWO rules, and the second is what this bead adds:

      * An AUTHOR outranks an editor and can always take a lock back --
        including from another author. That preemption IS the stale-lock
        release; there is no timer, because a clock that steals from someone
        actively working is worse than a human deciding to take it.
      * SAME-ROLE contention is now REFUSED when the server can tell the two
        people apart. Under shared tokens it could not, so it allowed the
        steal rather than pretending; now that a lock names a uid, an editor
        taking another editor's kit is a real collision and is blocked.

    The fallback matters as much as the rule: a lock with NO uid (written
    before this bead) is unattributable, so same-role contention stays
    ALLOWED for it. Refusing would strand an editor on a lock nobody can be
    shown to hold.
    """
    if holder == "author" and not actor.is_author:
        # NAME the author when we know them. This is the refusal an editor
        # most needs a name for: they cannot preempt an author, so their only
        # way forward is to go ask that person. Naming the other EDITOR while
        # leaving "an author" anonymous had it exactly backwards.
        who = holder_label or "An author"
        return (
            f"{who} is working on this form right now, so it is locked. "
            "They will release it when they are done."
        )
    # Author preemption: an author may always take over, from anyone.
    if actor.is_author:
        return None
    if holder_uid and holder_uid != actor.uid:
        who = holder_label or "Another editor"
        return (
            f"{who} is working on this form right now, so it is locked. "
            "They will release it when they are done."
        )
    return None


def _require_edit_lock(meta: Optional[dict], actor: EditorActor) -> None:
    """Refuse a schema write when someone else holds this kit for editing.

    One helper rather than five copies: bd polyglot-pdf-6dz0 and 6x1j both shipped
    a guard applied to ONE of N sibling routes, and both times the other N-1 were
    found by a reviewer rather than by me. The enumeration that found this gap is
    reproducible -- every route containing put_schema must call this.
    """
    holder = _lock_holder(meta)
    if not holder:
        return
    refusal = _lock_refusal(holder, actor, _lock_holder_uid(meta),
                            _lock_holder_label(meta))
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)


def _normalize_author_version(value: object) -> str:
    """The author-version normalization rule, in ONE place (bd polyglot-pdf-xzw5).

    Trim, then strip a leading v/V ONLY when a digit follows -- so "v2" becomes
    "2" while "version-3" is left intact. Returns "" for anything unusable
    (non-string, blank, or a bare "v").

    Every comparison and every write goes through this. Normalizing inside one
    branch and comparing raw values in another made a legitimate republish
    ("v2026-01-01" against a stored "2026-01-01") 409 as if the revision had
    changed. Mirrored in schema-editor/src/components/AuthorVersionDialog.tsx
    (normalizeAuthorVersion), with the same cases pinned on both sides.
    """
    if not isinstance(value, str):
        return ""
    return re.sub(r"^[vV](?=[0-9])", "", value.strip()).strip()


def _status_of(meta: Optional[dict]) -> str:
    status = (meta or {}).get("status")
    return status if status in _KIT_STATUSES else "unknown"


def _is_write_locked(meta: Optional[dict]) -> bool:
    """True when this kit's schema must not be rewritten in place."""
    return _status_of(meta) in _WRITE_LOCKED_STATUSES


def _lock_reason(meta: Optional[dict]) -> str:
    """The 409 detail for a write refused by the lock, naming the real state."""
    if _status_of(meta) == "submitted":
        return (
            "This form is submitted for review, so it is frozen while an "
            "author checks it -- otherwise they would review one version and "
            "publish another. Revert it to draft if you need to keep working "
            "on it."
        )
    if _status_of(meta) == "unpublished":
        return (
            "This form is unpublished (a superseded revision). Its schema is "
            "what earlier confirmation records were confirmed against, so it "
            "cannot be edited -- publish it again if you need to change it, "
            "which archives the retired copy first."
        )
    return (
        "This form is published (status complete). Revert it to draft first, "
        "then edit -- otherwise work-in-progress would go live to users "
        "immediately."
    )


# The kit's persisted AcroForm dump artifact filename (bd polyglot-pdf-v96b). The
# extract route writes it; the promotion-gate lint and the P5.3c widget picker
# read it.
_ACROFORM_ARTIFACT = "acroform.json"


async def _load_kit_dump(store, kit_id: str) -> Optional[dict]:
    """The kit's stored AcroForm dump, or None when absent/unreadable.

    Best-effort: a missing dump (FormKitNotFound) is the common pre-v96b case
    and simply means "no dump" -- callers degrade to the dump-less lint/repair
    path. A present-but-unreadable dump (FormKitStoreError) also degrades to None
    rather than failing the caller: the dump only ENRICHES lint (the widget-claim
    rule); it must never turn a promotable schema un-promotable by being corrupt.
    """
    try:
        dump = await store.load_json_artifact(kit_id, _ACROFORM_ARTIFACT)
    except (FormKitNotFound, FormKitStoreError):
        return None
    return dump if isinstance(dump, dict) else None


# --------------------------------------------------------------------------- #
# Readiness stamps (sprint-18 C4, bd polyglot-pdf-g687)
# --------------------------------------------------------------------------- #
#
# The catalogue used to answer "how much of this kit is reviewed?" by re-reading
# every kit's schema and recomputing -- so the number depended on WHICH surface
# last computed it. Now a SAVE records the answer in metadata.json and the
# catalogue reads that stamp. The counts come from publish_readiness, the same
# function the strip mirrors and (C2) the publish gate will refuse on.
#
# `verified` is the honesty bit. It is True only when the counts were computed
# against a real lint report; when lint could not run, the stamp still records
# what it knows but marks itself unverified, and the card renders the
# "not fully checked" hint instead of a confident percentage (decision 4). A
# stamp is also only meaningful for the schema it measured, so it carries that
# schema's hash, so a caller HOLDING the schema can tell the stamp no longer
# describes it. The catalogue listing holds no schema (not re-reading every kit
# is the point), so today the hash is recorded but not yet compared there --
# bd polyglot-pdf-j8sr tracks the routes that rewrite a schema without
# re-stamping, which is the reachable way a stamp goes stale in-app.

_READINESS_KEY = "readiness"


def _require_int(value):
    """The value if it is INTEGRAL, else raise so the caller yields None.

    Rejects bool (True is an int in Python) and str, which `int()` would
    happily coerce and the client's parser rejects. Accepts an integral FLOAT
    (75.0) because JSON has one number type: `json.loads('{"p": 75.0}')` gives
    a Python float while `JSON.parse` gives 75, so rejecting it here would make
    the same file parse in local mode and not in hosted -- and 75.0 is exactly
    what any jq / Python round-trip of the stamp produces (Opus outer review).
    A non-integral float (75.9) is still rejected, matching Number.isInteger.
    """
    if isinstance(value, bool):
        raise TypeError("expected int")
    if isinstance(value, float):
        if not value.is_integer():
            raise TypeError("expected integral value")
        return int(value)
    if not isinstance(value, int):
        raise TypeError("expected int")
    return value


def _require_str(value):
    """The value if it is a real string, else raise so the caller yields None.

    TypeError is one of the exceptions _readiness_out already catches, so a
    non-string hash degrades the whole stamp to "absent" (the verify hint)
    rather than fabricating one.
    """
    if not isinstance(value, str):
        raise TypeError("expected str")
    return value


def _readiness_out(meta: Optional[dict]):
    """Parse a kit's stored readiness stamp into the wire model, or None.

    Tolerant on purpose: a hand-edited, truncated, or older-shaped stamp yields
    None (the card falls back to the verify hint) rather than 502-ing a whole
    catalogue listing over one bad kit -- the same "one malformed kit must not
    hide the rest" rule the listing already follows for metadata.
    """
    raw = (meta or {}).get(_READINESS_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        stamp = ReadinessStamp(
            # Typed, not int()-coerced: int("75") is 75 and int(75.9) is 75,
            # where the client's parser (readinessStamp.readStampFromMetadata,
            # which requires Number.isInteger) rejects both and shows the
            # verify hint. Same file, two readings by mode -- the divergence
            # this bead exists to end (Opus fresh-eyes round 5; round 6 found
            # this comment had over-claimed -- the client accepted floats until
            # its `num()` was tightened to match).
            reviewed=_require_int(raw["reviewed"]),
            toReview=_require_int(raw["toReview"]),
            total=_require_int(raw["total"]),
            errors=_require_int(raw["errors"]),
            percent=_require_int(raw["percent"]),
            # `is True` for the SAME reason as `verified` below -- bool("no") is
            # True, and the client's parser requires an exact `=== true`, so a
            # loose read here means one metadata.json yields two answers
            # depending on which mode reads it (Opus fresh-eyes round 5: this
            # sibling boolean was missed one line above the round-4 fix).
            # `.get`, not `[...]`: an ABSENT flag must read as False, exactly
            # as the client's `r.ready === true` does. Requiring the key made
            # Python drop the whole stamp (the "not measured yet" hint) where
            # the client kept it and rendered a percentage -- the strictness
            # was mirrored but the required-vs-optional shape was not, leaving
            # the fix one step short (Opus outer review).
            ready=raw.get("ready") is True,
            # `is True`, NOT bool(): bool("no") is True, so a hand-edited or
            # older-shaped stamp carrying a STRING would promote itself from
            # "not fully checked" to a confident percentage on every card --
            # the exact confident-then-409 lie this flag exists to prevent.
            # The client's parser already required `=== true`; this is the
            # wire converter catching up (Opus fresh-eyes round 4).
            # `.get` for the same reason as `ready` above -- and the safe
            # direction besides: an absent flag means "no claim that the checks
            # ran", which is exactly UNVERIFIED.
            verified=raw.get("verified") is True,
            # Likewise typed, not str()-coerced: str(None) is the string
            # "None", which would later read as a hash that merely fails to
            # match -- i.e. STALE ("this form changed") rather than absent.
            # Latent until bd polyglot-pdf-j8sr compares hashes, and a wrong
            # diagnosis is worse than none.
            schemaSha1=_require_str(raw["schema_sha1"]),
            # A junk timestamp DEGRADES to None rather than failing the whole
            # stamp: it is decoration (nothing gates on it), and the client's
            # parser keeps the stamp in that case. Dropping the stamp here
            # would mean a card showing the verify hint in hosted mode and a
            # percentage in local mode for one file (Opus fresh-eyes round 5).
            stampedAt=(raw.get("stamped_at")
                       if isinstance(raw.get("stamped_at"), str) else None),
        )
    except (KeyError, TypeError, ValueError):
        return None
    # RANGE, not just type: a hand-edited `percent: 999` is exactly the
    # "hand-edited, truncated, or older-shaped stamp" this parser promises to
    # reject, and the card renders the percentage as a bar width -- a 999% bar
    # (Opus outer review). Negative counts are the same shape. Mirrored in the
    # client's readStampFromMetadata so the two still agree.
    if not 0 <= stamp.percent <= 100:
        return None
    if min(stamp.reviewed, stamp.toReview, stamp.total, stamp.errors) < 0:
        return None
    return stamp


def _schema_hash(schema: dict) -> str:
    """A stable content hash of the schema the stamp measured.

    Canonical JSON (sorted keys, no incidental whitespace) so re-serializing an
    unchanged schema cannot alter the hash. Its ONLY job is equality against a
    later read, so a fast digest is right; this is not a security boundary.
    """
    blob = json.dumps(schema, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _readiness_stamp(schema: dict, findings, verified: bool) -> dict:
    """The metadata.json `readiness` block for a saved schema."""
    verdict = publish_readiness(schema, findings)
    return {
        **verdict.counts.as_dict(),
        "ready": verdict.ready,
        "verified": bool(verified),
        "schema_sha1": _schema_hash(schema),
        "stamped_at": datetime.now(timezone.utc).isoformat(),
    }


_METADATA_FILE = "metadata.json"


async def _stamp_readiness(store, kit_id: str, schema: dict,
                           meta: Optional[dict],
                           files: Optional[set] = None) -> Optional[dict]:
    """Compute and persist a kit's readiness stamp; return the stamp.

    Best-effort BY DESIGN: a stamp is a display/gate convenience, never the
    user's work. If lint or the metadata write fails, the SAVE it rides along
    with must still succeed -- losing an editor's schema edit because a
    progress number could not be computed would be a far worse bug than a card
    that shows the verify hint until the next save. A lint failure degrades to
    an UNVERIFIED stamp (honest: counts without a checked lint report) rather
    than to no stamp at all.
    """
    try:
        # NOT _load_kit_dump here (bd polyglot-pdf-kwh3t): that helper
        # collapses BOTH FormKitNotFound (the legitimate pre-v96b "no dump"
        # case) and FormKitStoreError (a corrupt/transient-unreadable
        # acroform.json) to None -- so a lint that ran dump-BLIND because the
        # READ failed looked identical to one that ran dump-blind because
        # there was genuinely never a dump, and stamped verified=True either
        # way. That silently missed the two dump-gated rules
        # (dump-widget-multiclaim ERROR, dump-widget-unclaimed WARNING) while
        # the stamp claimed the checks ran. Mirrors POST /kits/{kit_id}/lint's
        # own read (see that route's comment): a missing dump is fine, a
        # FAILED read must degrade to unverified, matching the open editor's
        # strip's degraded state for the identical kit.
        try:
            raw_dump = await store.load_json_artifact(kit_id, _ACROFORM_ARTIFACT)
            dump = raw_dump if isinstance(raw_dump, dict) else None
        except FormKitNotFound:
            dump = None
        findings = lint_schema(schema, dump)
        verified = True
    except Exception:  # noqa: BLE001 -- see the docstring: never fail the save
        _log.warning("editor_readiness_lint_failed", kit_id=kit_id, exc_info=True)
        findings = []
        verified = False
    # `meta is None` means EITHER the file is ABSENT or it is UNPARSEABLE --
    # both stores collapse the two to None -- and the right action differs:
    #
    #   unparseable -> SKIP. Merging into `{}` would replace a corrupt but
    #     recoverable file with just the stamp, deleting the kit's status,
    #     label and any custom schema/pdf filenames (a complete kit would
    #     silently unpublish -- deploy-all.sh greps `status` -- and a kit
    #     pointing at custom.json would orphan its real schema). Pre-C4 the
    #     save wrote no metadata at all, so a corrupt file passed through
    #     untouched; this diff must not make an ordinary Cmd+S destructive.
    #   absent -> STAMP into a fresh dict. A metadata-less kit is a normal,
    #     shipped state (form-kits/w9-heldout has no metadata.json), and there
    #     is nothing to lose. Round 6 collapsed both cases into "skip", which
    #     meant such a kit could never show a percentage however many times it
    #     was saved (Opus fresh-eyes rounds 6 + 7).
    #
    # `files` is the kit's filename set, already in the caller's hand from
    # _load_meta_or_404 -- no extra store round-trip to tell the cases apart.
    if meta is None:
        unparseable = files is not None and _METADATA_FILE in files
        if unparseable:
            _log.warning("editor_readiness_stamp_skipped_bad_metadata",
                         kit_id=kit_id)
            return None
        if files is None:
            # No filename set supplied: cannot distinguish, so take the SAFE
            # branch (never destroy). Callers that can tell should pass it.
            _log.warning("editor_readiness_stamp_skipped_no_metadata",
                         kit_id=kit_id)
            return None
        meta = {}
    try:
        stamp = _readiness_stamp(schema, findings, verified)
        await store.put_metadata(kit_id, {**meta, _READINESS_KEY: stamp})
    except Exception:  # noqa: BLE001 -- see the docstring: never fail the save
        # Deliberately broad, and load-bearing rather than defensive: the schema
        # is ALREADY written by the time this runs, so ANY exception escaping
        # here would turn a successful save into a 500 the editor reports as
        # "save failed" -- the human then re-saves or, worse, believes their
        # work was lost. Catching only FormKitStoreError left every other
        # failure (a store lacking put_metadata, an unserializable stamp) doing
        # exactly that; caught by test_put_schema_refuses_published_kit.
        _log.warning("editor_readiness_stamp_failed", kit_id=kit_id, exc_info=True)
        return None
    return stamp


@router.get("/session", response_model=EditorSessionResponse)
async def editor_session(
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> EditorSessionResponse:
    """Sign-in probe: the hosted editor calls this once the person signs in,
    to learn their role (author-only UI is gated on it) and to confirm they
    hold editor access AT ALL before any kit traffic.

    A 403 here is the gate's cue to show its refused screen rather than the
    sign-in form -- see editor_auth.NO_EDITOR_ACCESS_PREFIX for why the two
    kinds of 403 must stay distinguishable on the wire."""
    return EditorSessionResponse(role=role.role)


# The handshake file the editor drops into the picked folder. Written and
# deleted by the BROWSER; the backend only ever READS it.
_HANDSHAKE_FILE = ".editor-store-check.json"


@router.post("/store-handshake", response_model=StoreHandshakeResponse)
async def editor_store_handshake(
    body: StoreHandshakeBody,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> StoreHandshakeResponse:
    """Confirm the editor and the backend are looking at the SAME folder.

    See StoreHandshakeBody for why this exists and why it is a nonce rather
    than a path comparison. The editor writes `.editor-store-check.json` into
    the folder the human picked; this reads that file from the backend's own
    root and reports whether the nonce matches.

    Read-only on the backend side: it never creates or deletes the file, so a
    store it cannot read simply reports sameFolder=false with
    reason="mismatch" (nothing readable was observed at its own root)
    instead of failing. The editor knows whether its own marker WRITE
    failed -- it just tried it -- so it picks the user-facing message;
    this route only reports what it saw.
    """
    store = get_form_kit_store()
    if not isinstance(store, LocalFormKitStore):
        # A GCS-backed store shares no directory with the browser, so there is
        # nothing to agree on. Hosted mode does not call this.
        return StoreHandshakeResponse(
            sameFolder=False, reason="not-a-local-store")

    root = Path(store.root)
    path = root / _HANDSHAKE_FILE

    def _read() -> Optional[str]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data.get("nonce") if isinstance(data, dict) else None

    seen = await anyio.to_thread.run_sync(_read)
    if seen is None:
        # Either the editor is pointed somewhere else, or it could not write
        # its marker. The editor knows which -- it just tried the write -- so
        # it picks the message; this only reports that nothing was observed.
        return StoreHandshakeResponse(
            sameFolder=False, backendRoot=str(root), reason="mismatch")
    if seen != body.nonce:
        # A STALE marker from an earlier session in a different folder. Same
        # verdict, but worth distinguishing from "no file at all".
        return StoreHandshakeResponse(
            sameFolder=False, backendRoot=str(root), reason="stale")
    return StoreHandshakeResponse(sameFolder=True, backendRoot=str(root))


@router.get("/kits", response_model=EditorKitListResponse)
async def list_editor_kits(
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> EditorKitListResponse:
    """Every kit in the store, DRAFTS INCLUDED -- the contractor work list.

    Built from one storage listing (list_kit_files) + each kit's metadata.json,
    never from the complete-only index.json manifest. A kit whose metadata is
    missing/unreadable still lists (status unknown, conventional filenames) --
    one malformed kit must not hide the rest.
    """
    store = get_form_kit_store()
    try:
        files_by_kit = await store.list_kit_files()
    except FormKitStoreError as exc:
        _log.error("editor_kits_list_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to list kits") from exc

    kits: list[EditorKitInfo] = []
    for kit_id in sorted(files_by_kit):
        # Skip ids the single-kit routes would reject (defense in depth: such a
        # folder could never be opened, so listing it would be a dead card).
        try:
            _safe_kit_id(kit_id)
        except HTTPException:
            continue
        try:
            meta = await store.load_metadata(kit_id)
        except FormKitStoreError:
            meta = None  # unreadable metadata -> list with unknowns, don't 502
        schema_file, pdf_file = _resolve_meta_names(meta)
        names = set(files_by_kit[kit_id])
        label = (meta or {}).get("label")
        description = (meta or {}).get("description")
        kits.append(
            EditorKitInfo(
                id=kit_id,
                label=label if isinstance(label, str) and label else kit_id,
                description=description if isinstance(description, str) else None,
                status=_status_of(meta),
                heldBy=_lock_holder(meta),
                heldByLabel=_lock_holder_label(meta),
                hasSchema=schema_file in names,
                hasPdf=pdf_file in names,
                schemaFile=schema_file,
                pdfFile=pdf_file,
                # Rides along on the metadata this loop already read -- no extra
                # per-kit fetch (sprint-18 C4).
                readiness=_readiness_out(meta),
            )
        )
    _log.info("editor_kits_listed", count=len(kits), role=role.role, actor=role.label())
    return EditorKitListResponse(kits=kits)


async def _load_meta_or_404(store, kit_id: str) -> tuple[Optional[dict], set[str]]:
    """The kit's (metadata, filenames) -- 404 when the kit isn't in the store.

    Existence = presence in the storage listing (a kit is its folder), NOT
    presence in the manifest: drafts are exactly the kits the editor works on.

    A FAILED metadata read (FormKitStoreError) propagates as 502 -- it must NOT
    degrade to None: metadata.status is the GUARD input for the write paths
    (the publish gate refuses saves on complete kits), so suppressing a
    transient read failure would let a save land on a possibly-published kit
    (Codex P1 r2, PR #279). Only the LIST route tolerates unreadable metadata
    (one bad kit must not hide the rest), and it does so with its own catch.
    """
    try:
        files_by_kit = await store.list_kit_files()
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to list kits") from exc
    if kit_id not in files_by_kit:
        raise HTTPException(status_code=404, detail=f"Unknown kit: {kit_id}")
    try:
        meta = await store.load_metadata(kit_id)
    except FormKitStoreError as exc:
        raise HTTPException(
            status_code=502, detail="Unable to read kit metadata"
        ) from exc
    return meta, set(files_by_kit[kit_id])


# _archive_published_revision now lives in backend/services/kit_gates.py
# (imported above): bd polyglot-pdf-z6bk9 gave it a SECOND caller in the
# client-tier routes, and routes importing routes would be circular --
# editor_kit_routes already imports _safe_kit_id from form_kit_routes.


class RetireCandidate(BaseModel):
    """One live kit that MIGHT be an older revision of the kit being published.

    Every field here exists to let a human tell two same-numbered kits apart,
    because the system cannot: form_number is explicitly NOT unique (a standard
    W-7 and a firm's own W-7 variant share it -- see
    docs/standards/confirmation-and-audit.md), and the label is free text an
    author may rename. That is exactly why this is a SUGGESTION and a person
    confirms (maintainer decision 2026-08-07).
    """

    kitId: str
    label: str
    # The form NUMBER ("W-7"), when its schema declares one.
    formNumber: Optional[str] = None
    # Whichever revision marker this kit actually carries, and which one it is,
    # so the UI can say "edition 12/2024" rather than showing a bare string
    # whose meaning it has to guess.
    edition: Optional[str] = None
    editionKind: Optional[str] = None  # "edition_date" | "author_version" | "published"
    # Why this kit was suggested. Shown to the author: a label-similarity match
    # deserves more suspicion than a form-number match.
    matchedOn: str  # "form_number" | "label"


class RetireCandidatesResponse(BaseModel):
    candidates: list[RetireCandidate]


def _identity_of_schema(schema: Optional[dict]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(form_number, edition, edition_kind) from a kit's schema.

    Mirrors resolve_edition_marker's PRECEDENCE (edition_date > author_version)
    but not its fingerprint fallback: a sha256 shown to a human is noise, and
    this value exists only to disambiguate two candidates on screen.
    """
    block = (schema or {}).get("form_metadata")
    block = block if isinstance(block, dict) else {}

    def _clean(v: object) -> Optional[str]:
        return v.strip() if isinstance(v, str) and v.strip() else None

    number = _clean(block.get("form_number"))
    edition = _clean(block.get("edition_date"))
    if edition:
        return number, edition, "edition_date"
    version = _clean(block.get("author_version"))
    if version:
        return number, version, "author_version"
    return number, None, None


def _normalize_label(label: str) -> str:
    """Lowercased alphanumerics only -- 'W-7 (ITIN Application)' -> 'w7itinapplication'."""
    return "".join(ch for ch in label.lower() if ch.isalnum())


def _labels_look_like_one_form(a: str, b: str) -> bool:
    """A deliberately CONSERVATIVE label match: EQUALITY after normalising.

    Containment is unsafe here, at any slack. Real form families differ by a
    one- or two-character suffix, and those variants are DIFFERENT FORMS --
    several are supplements filed ALONGSIDE their base form, so retiring one
    breaks a live filing path:

        I-130 / I-130A      I-864 / I-864A / I-864EZ
        I-129 / I-129F      I-131 / I-131A
        I-765 / I-765V      1040 / 1040-X
        1099 / 1099-MISC    W-8BEN / W-8BEN-E
        941 / 941-X

    My first version allowed a short suffix, reasoning that "Client Intake"
    vs "Client Intake Sheet" is a rename. It is -- but the rule could not tell
    that from I-130 vs I-130A, and it admitted every pair above (Opus
    fresh-eyes round 1). Slack of 5, 6, 7 or 8 all passed my tests, because
    they only sampled LONG suffixes; the dimension was untested.

    So: exact match only, and let the rename case cost an author one manual
    retire. This rule is the FALLBACK anyway -- it fires only for kits that
    declare no form_number, and the number is the signal that should carry
    real matches. A missed suggestion costs a click; a wrong one asks an
    author to retire a live form, possibly another firm's, possibly one a
    pending filing depends on.
    """
    na, nb = _normalize_label(a), _normalize_label(b)
    # The floor exists only to reject DEGENERATE labels (empty, or a single
    # stray character), not real ones. At 3 it silently killed the commonest
    # real form labels: "W-7" normalises to "w7", two characters -- as do W-2,
    # W-4, W-9 and I-9. Two kits both labelled "W-7" with no form_number
    # declared produced NO candidate, so an author published a second live W-7
    # believing there was no older version: exactly the state bd
    # polyglot-pdf-6dz0 exists to prevent (Opus fresh-eyes round 3).
    #
    # Exact match already carries the safety here; the floor only needs to stop
    # a one-character label matching another one-character label.
    if len(na) < 2 or len(nb) < 2:
        return False
    return na == nb


class DraftSnapshot(BaseModel):
    """One recoverable prior state of a kit's draft schema."""

    id: str
    savedAt: Optional[str] = None


class DraftSnapshotsResponse(BaseModel):
    snapshots: list[DraftSnapshot]


class RestoreSnapshotResponse(BaseModel):
    ok: bool
    kitId: str
    restoredFrom: str
    # The snapshot taken of the work being replaced, so a restore is itself
    # undoable -- see the route docstring.
    snapshotOfReplaced: Optional[str] = None


@router.get("/kits/{kit_id}/draft-snapshots",
            response_model=DraftSnapshotsResponse)
async def list_kit_draft_snapshots(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> DraftSnapshotsResponse:
    """Prior saved states of this kit's draft, newest first.

    EDITOR-accessible, deliberately (maintainer decision 2026-08-18). The
    principle this serves is that an editor's work must be recoverable -- and
    routing recovery through an author means the person who lost the work
    cannot get it back themselves, which is most of the value gone.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    # 404 for a kit that does not exist, rather than an empty list: "you have
    # no earlier versions" and "that form does not exist" are different
    # answers, and conflating them is the false-negative direction in a
    # recovery feature (Opus fresh-eyes round 4).
    await _load_meta_or_404(store, kit_id)
    try:
        snapshots = await store.list_draft_snapshots(kit_id)
    except FormKitStoreError as exc:
        _log.error("draft_snapshots_list_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(
            status_code=502, detail="Unable to list earlier versions") from exc
    _log.info("draft_snapshots_listed", kit_id=kit_id, count=len(snapshots), role=role.role, actor=role.label())
    return DraftSnapshotsResponse(
        snapshots=[DraftSnapshot(**s) for s in snapshots])


class ArchivedRevisionEntry(BaseModel):
    """One superseded revision (bd polyglot-pdf-qfyxr): the ENCODED archive
    marker (the path segment under <kit>/_archive/) plus the archived
    metadata snapshot's published_at (None when the snapshot predates the
    stamp or is missing)."""
    marker: str
    published_at: Optional[str] = None


class ArchivedRevisionsResponse(BaseModel):
    revisions: list[ArchivedRevisionEntry]


# The marker contract lives in kit_gates.is_safe_marker (ONE definition for
# the client + editor archive routes); this wrapper only maps refusal to 400.
def _safe_archive_marker(marker: str) -> str:
    if not is_safe_marker(marker):
        raise HTTPException(status_code=400, detail="Invalid revision marker")
    return marker


@router.get("/kits/{kit_id}/archive", response_model=ArchivedRevisionsResponse)
async def list_kit_archive(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> ArchivedRevisionsResponse:
    """This kit's superseded revisions, NEWEST FIRST (bd polyglot-pdf-qfyxr).

    EDITOR-accessible: the archive is read-only history (the bytes old
    confirmation records name), so reading it risks nothing an editor could
    corrupt -- same reasoning as draft snapshots above. Sorted newest-first
    by the archived snapshot's published_at; stampless revisions sort last.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    # 404 for a kit that does not exist rather than an empty list -- "no
    # archived versions" and "no such form" are different answers (the
    # draft-snapshots lesson, Opus fresh-eyes round 4 there).
    await _load_meta_or_404(store, kit_id)
    try:
        markers = await store.list_archived_markers(kit_id)
        snapshots = await asyncio.gather(
            *(store.load_archived_metadata_or_none(kit_id, m) for m in markers)
        )
    except FormKitStoreError as exc:
        _log.error("kit_archive_list_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(
            status_code=502, detail="Unable to list archived revisions") from exc
    revisions = []
    for marker, snapshot in zip(markers, snapshots):
        stamp = (snapshot or {}).get("published_at")
        revisions.append(ArchivedRevisionEntry(
            marker=marker,
            published_at=stamp if isinstance(stamp, str) else None,
        ))
    revisions.sort(
        key=lambda r: (r.published_at is not None, r.published_at or ""),
        reverse=True,
    )
    _log.info("kit_archive_listed", kit_id=kit_id, count=len(revisions), role=role.role, actor=role.label())
    return ArchivedRevisionsResponse(revisions=revisions)


@router.get("/kits/{kit_id}/archive/{marker}/schema")
async def get_archived_kit_schema(
    kit_id: str,
    marker: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> JSONResponse:
    """An archived revision's schema, READ-ONLY (bd polyglot-pdf-qfyxr).

    There is deliberately no write counterpart: a superseded revision is what
    the audit trail references, and editing it would corrupt those bytes --
    the exact corruption the unpublished write-lock exists to prevent.
    Returning to an old revision goes through the normal draft/publish flow,
    never through the archive.
    """
    kit_id = _safe_kit_id(kit_id)
    marker = _safe_archive_marker(marker)
    store = get_form_kit_store()
    await _load_meta_or_404(store, kit_id)
    try:
        schema = await store.load_archived_revision(kit_id, marker)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Archived revision not found for kit {kit_id}") from exc
    except FormKitStoreError as exc:
        _log.error(
            "kit_archive_read_failed", kit_id=kit_id, marker=marker, error=str(exc))
        raise HTTPException(
            status_code=502, detail="Unable to load archived revision") from exc
    return JSONResponse(content=schema, headers={"Cache-Control": "no-store"})


@router.post("/kits/{kit_id}/draft-snapshots/{snapshot_id}/restore",
             response_model=RestoreSnapshotResponse)
async def restore_kit_draft_snapshot(
    kit_id: str,
    snapshot_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> RestoreSnapshotResponse:
    """Put a snapshot's schema back as the live draft.

    A restore is itself a WRITE over someone's current work, so it snapshots
    what it replaces FIRST -- restoring the wrong version is then one more
    restore away, not a second loss. That is what makes it safe to let an
    editor do this without waiting for an author.

    Refused on a write-locked kit for the same reason a save is: a complete or
    unpublished revision is what confirmation records name, and reopening one
    goes through the explicit revert-to-draft, never a side door.
    """
    kit_id = _safe_kit_id(kit_id)
    if not (snapshot_id.isascii() and snapshot_id.isdigit()):
        # Snapshot ids are the store's own monotonic counter. Anything else is
        # a caller constructing a path, and it never reaches the store.
        raise HTTPException(status_code=400, detail="Invalid snapshot id")

    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    if _is_write_locked(meta):
        raise HTTPException(status_code=409, detail=_lock_reason(meta))
    _require_edit_lock(meta, role)

    try:
        restored = await store.load_draft_snapshot(kit_id, snapshot_id)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"No earlier version {snapshot_id} for this form",
        ) from exc
    except FormKitStoreError as exc:
        _log.error("draft_snapshot_read_failed",
                   kit_id=kit_id, snapshot=snapshot_id, error=str(exc))
        raise HTTPException(
            status_code=502, detail="Unable to read that earlier version") from exc

    schema_file, _pdf = _resolve_meta_names(meta)

    # Snapshot the CURRENT work before replacing it. Unlike the save path this
    # is NOT best-effort: a restore knowingly destroys the current draft, so
    # refusing when we cannot protect it first is the honest failure. A
    # recovery feature that loses work is worse than one that declines.
    replaced_id: Optional[str] = None
    try:
        current = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound:
        # No schema yet -- there is genuinely nothing to protect.
        current = None
    except FormKitStoreError as exc:
        # NOT the same thing: the work IS there and we could not read it.
        # Collapsing these two into `current = None` skipped the pre-restore
        # snapshot and fell straight through to put_schema, permanently
        # destroying bytes that were never copied anywhere -- and returning
        # 200. A transient GCS 503 during a restore was enough to lose an
        # editor's current draft while telling them it worked.
        #
        # The write side below already refuses on failure; this is the read
        # side of the same guarantee (Opus fresh-eyes round 5).
        _log.error("draft_snapshot_pre_restore_read_failed",
                   kit_id=kit_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=("Could not read your current work before restoring, so "
                    "the restore was refused. Nothing was changed."),
        ) from exc
    if current is not None:
        try:
            replaced_id = await store.put_draft_snapshot(kit_id, current)
        except FormKitStoreError as exc:
            _log.error("draft_snapshot_pre_restore_failed",
                       kit_id=kit_id, error=str(exc))
            raise HTTPException(
                status_code=502,
                detail=("Could not save your current work before restoring, so "
                        "the restore was refused. Nothing was changed."),
            ) from exc

    try:
        await store.put_schema(kit_id, restored, schema_file)
    except FormKitStoreError as exc:
        _log.error("draft_snapshot_restore_failed",
                   kit_id=kit_id, snapshot=snapshot_id, error=str(exc))
        raise HTTPException(
            status_code=502, detail="Unable to restore that earlier version") from exc

    _log.info("draft_snapshot_restored", kit_id=kit_id, snapshot=snapshot_id,
              replaced_snapshot=replaced_id, role=role.role, actor=role.label())
    return RestoreSnapshotResponse(
        ok=True, kitId=kit_id, restoredFrom=snapshot_id,
        snapshotOfReplaced=replaced_id)


@router.get("/kits/{kit_id}/retire-candidates",
            response_model=RetireCandidatesResponse)
async def get_retire_candidates(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
) -> RetireCandidatesResponse:
    """LIVE kits that plausibly serve the same form as this one.

    Suggestion only -- nothing is retired here. The author ticks one on the
    publish modal, which sends it as `replaces_kit_id` to the status route,
    which is what actually retires it (bd polyglot-pdf-6dz0).

    AUTHOR-ONLY, matching the publish it feeds: an editor cannot publish, so
    offering them a retire list would be a control they cannot use -- and the
    list itself is a statement about which kits exist.

    Reads each live kit's schema, which the catalogue listing deliberately does
    NOT do (one metadata read per kit keeps that path cheap). Confined to this
    route so the cost lands only when an author is actually publishing.

    A kit whose schema cannot be read is SKIPPED, not surfaced with unknowns: a
    candidate you cannot describe is one the author cannot judge, and the whole
    point is an informed confirmation.
    """
    # Every sibling route in this file opens this way. Traversal is
    # impractical today (the membership check in _load_meta_or_404 is what
    # actually guards it), but this route was the one exception to a uniform
    # invariant, and the guard is what makes that membership check safe to rely
    # on (Opus fresh-eyes round 3).
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    _meta, _files = await _load_meta_or_404(store, kit_id)

    schema_file, _pdf = _resolve_meta_names(_meta)
    try:
        own_schema = await store.load_schema(kit_id, schema_file)
    except (FormKitNotFound, FormKitStoreError):
        own_schema = None
    own_number, _own_ed, _own_kind = _identity_of_schema(own_schema)
    own_label = (_meta or {}).get("label")
    own_label = own_label if isinstance(own_label, str) and own_label else kit_id

    try:
        files_by_kit = await store.list_kit_files()
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to list kits") from exc

    candidates: list[RetireCandidate] = []
    for other_id in sorted(files_by_kit):
        if other_id == kit_id:
            continue
        try:
            _safe_kit_id(other_id)
        except HTTPException:
            continue
        try:
            other_meta = await store.load_metadata(other_id)
        except FormKitStoreError as exc:
            # LOUD, not silent. Skipping quietly makes a storage blip
            # indistinguishable from "no older versions", so the author gets a
            # confident straight-through publish and two live kits for one form
            # -- the state bd polyglot-pdf-6dz0 exists to prevent (Opus
            # fresh-eyes round 1).
            _log.warning("editor_retire_candidate_unreadable",
                         kit_id=kit_id, candidate=other_id, error=str(exc))
            continue
        # LIVE only. A draft is not competing for the catalogue slot, and a
        # kit already unpublished has nothing left to retire.
        if _status_of(other_meta) != "complete":
            continue

        other_label = (other_meta or {}).get("label")
        other_label = other_label if isinstance(other_label, str) and other_label else other_id
        other_schema_file, _p = _resolve_meta_names(other_meta)
        try:
            other_schema = await store.load_schema(other_id, other_schema_file)
        except (FormKitNotFound, FormKitStoreError):
            continue  # cannot describe it -> cannot ask a human to judge it
        other_number, other_ed, other_kind = _identity_of_schema(other_schema)

        # form_number FIRST, label similarity second (the bead's order): the
        # number is a real declaration, the label is free text.
        if own_number and other_number:
            # BOTH declare a number, so the declaration DECIDES -- in either
            # direction. Falling through to the label on a mismatch let the
            # weakest signal (free text an author can rename) override the
            # strongest one (an extracted declaration): with production data,
            # where every real kit declares a number, I-130 suggested retiring
            # I-130A whenever their labels happened to match. That is the
            # supplement-filed-alongside-its-base case, and the exact harm
            # auto-retire was rejected over -- arriving through the fallback
            # instead of the primary path (Opus fresh-eyes round 4).
            if own_number != other_number:
                continue
            matched = "form_number"
        elif _labels_look_like_one_form(own_label, other_label):
            matched = "label"
        else:
            continue

        if other_ed is None and other_kind is None:
            # No edition and no author version: fall back to when it went live,
            # so the author still has a date to tell two candidates apart.
            published = (other_meta or {}).get("published_at")
            if isinstance(published, str) and published.strip():
                other_ed, other_kind = published.strip(), "published"

        candidates.append(RetireCandidate(
            kitId=other_id,
            label=other_label,
            formNumber=other_number,
            edition=other_ed,
            editionKind=other_kind,
            matchedOn=matched,
        ))

    _log.info("editor_retire_candidates", kit_id=kit_id, count=len(candidates))
    return RetireCandidatesResponse(candidates=candidates)


@router.get("/kits/{kit_id}/schema")
async def get_editor_kit_schema(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> JSONResponse:
    """A kit's schema for editing -- unlike the public route this serves DRAFTS
    (filenames resolved from the kit's own metadata, not the manifest)."""
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _ = await _load_meta_or_404(store, kit_id)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema yet"
        ) from exc
    except FormKitStoreError as exc:
        _log.error("editor_schema_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc
    return JSONResponse(content=schema, headers={"Cache-Control": "no-store"})


@router.get("/kits/{kit_id}/pdf")
async def get_editor_kit_pdf(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> Response:
    """A kit's PDF bytes for the editor's viewer (drafts included)."""
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _ = await _load_meta_or_404(store, kit_id)
    _schema, pdf_file = _resolve_meta_names(meta)
    try:
        data = await store.load_pdf_bytes(kit_id, pdf_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no PDF"
        ) from exc
    except FormKitStoreError as exc:
        _log.error("editor_pdf_load_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to load PDF") from exc
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )


@router.put("/kits/{kit_id}/schema")
async def save_editor_kit_schema(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
    schema: Annotated[dict, Body()],
) -> dict:
    """Save a contractor's edited schema back to the store (the hosted Cmd+S).

    Lenient by design -- a draft mid-polish may be incomplete -- but never
    formless: it must be a JSON object with a `fields` list (the minimum the
    editor itself can reopen). Full FormSchema validation runs at the
    mark-complete gate, not here. Writes only to EXISTING kits (the kit's own
    schema filename from its metadata); creating kits is the author-tier
    onboarding route (bd 92qe.3).
    """
    kit_id = _safe_kit_id(kit_id)
    if not isinstance(schema.get("fields"), list):
        raise HTTPException(
            status_code=422,
            detail="Schema must be a JSON object with a 'fields' list",
        )
    store = get_form_kit_store()
    meta, kit_files = await _load_meta_or_404(store, kit_id)
    # A PUBLISHED (complete) kit's schema blob is exactly what the public read
    # routes stream to voice users, so a lenient draft save over it would go
    # live instantly, bypassing the promote-time validation gate (Codex P1,
    # PR #279). Require the explicit revert-to-draft first -- which unpublishes
    # the kit immediately (the public routes honor live status on the shared
    # store), so work-in-progress never reaches users.
    if _is_write_locked(meta):
        raise HTTPException(status_code=409, detail=_lock_reason(meta))
    # The EDITING lock, one layer over the status write-lock: an author who
    # took this kit back is mid-review, and a save from under them would mean
    # they approve something they never saw (bd polyglot-pdf-hqztg). This is
    # also where an editor DISCOVERS they were preempted -- there is no channel
    # from server to editor, so the next save is the notification.
    _require_edit_lock(meta, role)
    schema_file, _pdf = _resolve_meta_names(meta)

    # SNAPSHOT THE CURRENT SCHEMA FIRST (bd polyglot-pdf-y2l0p). Maintainer
    # principle, 2026-08-08: "Editors should not ever be able to make
    # destructive actions. Their work should always be recoverable."
    #
    # put_schema overwrites in place, and the write-lock above refuses only a
    # COMPLETE or UNPUBLISHED kit -- so a published revision was protected and
    # a DRAFT was not. Editor A's hours of work vanished when editor B (or A,
    # from a stale tab) saved over it, with no copy anywhere: the in-editor
    # undo stack is cleared on load, so it never survived a reload and never
    # covered a cross-session overwrite.
    #
    # BEST-EFFORT, deliberately. A snapshot failure must not block the save:
    # the editor's CURRENT work is what matters most, and refusing to save in
    # order to protect an older copy inverts the priority. Logged loudly
    # instead -- the same posture as the revision archive.
    try:
        existing = await store.load_schema(kit_id, schema_file)
    except (FormKitNotFound, FormKitStoreError):
        existing = None  # nothing to protect yet (first save of a new kit)
    if existing is not None:
        try:
            snapshot_id = await store.put_draft_snapshot(kit_id, existing)
            _log.info("editor_draft_snapshotted",
                      kit_id=kit_id, snapshot=snapshot_id, role=role.role, actor=role.label())
        except FormKitStoreError as exc:
            _log.warning("editor_draft_snapshot_failed",
                         kit_id=kit_id, error=str(exc))

    try:
        await store.put_schema(kit_id, schema, schema_file)
    except FormKitStoreError as exc:
        _log.error("editor_schema_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to save schema") from exc
    # Stamp the saved schema's readiness (sprint-18 C4). AFTER the schema write
    # and deliberately non-fatal: the save is the editor's work, the stamp is a
    # display convenience, so a stamp failure leaves the card showing the verify
    # hint rather than losing the edit.
    stamp = await _stamp_readiness(store, kit_id, schema, meta, kit_files)
    _log.info("editor_schema_saved", kit_id=kit_id, role=role.role, actor=role.label(),
              field_count=len(schema.get("fields", [])),
              readiness_percent=(stamp or {}).get("percent"),
              readiness_verified=(stamp or {}).get("verified"))
    return {"ok": True, "schemaFile": schema_file,
            **({"readiness": stamp} if stamp else {})}


@router.post("/lint", response_model=LintResponse)
async def lint_editor_schema(
    role: Annotated[EditorActor, Depends(require_editor_role)],
    schema: Annotated[dict, Body()],
) -> LintResponse:
    """Lint a schema and return structured findings for load-time display.

    The editor POSTs the schema it currently HOLDS (which may carry unsaved
    edits), not a kit id -- so the panel lints exactly what is on screen, before
    any save, over the same authoritative Python rules the mark-complete
    promotion gate uses (backend/services/schema_lint.py). This is P4.3's "single
    Python implementation": the frontend renders these findings instead of
    maintaining a parallel TS ruleset that could drift from the promotion gate.

    Never 4xx on schema shape -- lint_schema never raises, and a malformed draft
    IS the thing the contractor needs the findings for (a structural problem
    surfaces as a condition-malformed finding, not an HTTP error). No dump is
    passed: this route has no kit id, so it has no kit dump to load. An OPEN
    kit's editor lints through the kit-scoped POST /kits/{kit_id}/lint twin
    below, which loads acroform.json exactly as the promotion gate does -- this
    dump-less route remains for schemas with no kit identity (nothing opened
    from the store).
    """
    findings = lint_schema(schema)
    out = [LintFindingOut(**f.as_dict()) for f in findings]
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_schema_linted", role=role.role, actor=role.label(),
              errors=error_count, warnings=warning_count)
    return LintResponse(
        findings=out, errorCount=error_count, warningCount=warning_count,
    )


@router.post("/kits/{kit_id}/lint", response_model=LintResponse)
async def lint_editor_kit_schema(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
    schema: Annotated[dict, Body()],
) -> LintResponse:
    """Lint the POSTED schema WITH the kit's persisted AcroForm dump.

    The kit-scoped twin of POST /lint (sprint-18 C1, bd polyglot-pdf-o7y9).
    The dumpless route structurally cannot run the two dump-gated rules
    (dump-widget-multiclaim ERROR, dump-widget-unclaimed WARNING), so an
    editor strip fed by it could read clean -- and its progress reach a
    confident 100% -- while the promotion gate still 409s on a dump-only
    ERROR. This route loads acroform.json exactly as the /status complete
    gate does and passes it to the SAME lint_schema call, so the editor's
    live findings and the gate share one input set. The schema still comes
    from the request body (the on-screen, possibly-unsaved draft), never
    from the store: the strip lints what the human is looking at.

    A kit without a persisted dump (pre-v96b) degrades to the dump-less
    rules -- identical to the gate's own degradation, so the two still agree.
    """
    kit_id = _safe_kit_id(kit_id)
    if not isinstance(schema.get("fields"), list):
        raise HTTPException(
            status_code=422,
            detail="Schema must be a JSON object with a 'fields' list",
        )
    store = get_form_kit_store()
    # 404 for an unknown kit rather than silently linting dump-less: a typo'd
    # kit id must not masquerade as a legitimate no-dump kit. Existence is
    # probed with TWO direct reads (metadata + dump), NOT _load_meta_or_404:
    # that helper answers "does the kit exist" via list_kit_files, which on
    # the GCS store lists EVERY blob under form-kits/ -- a whole-bucket LIST
    # on the editor's hottest route, growing with total kit count (Opus outer
    # review). Every onboarded kit has metadata.json, so metadata-or-dump
    # present <=> the kit exists; both absent <=> 404. A transient store
    # failure on the metadata read surfaces as 502 via FormKitStoreError.
    try:
        meta = await store.load_metadata(kit_id)
    except FormKitStoreError as exc:
        _log.error("editor_kit_lint_meta_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to read kit") from exc
    # The dump read does NOT go through _load_kit_dump here: that helper
    # swallows transient store failures into "no dump", which on THIS route
    # would silently downgrade the lint to dump-blind and return a 200 the
    # strip presents as authoritative -- the exact confident-clean state the
    # route exists to end (Opus outer review, pass 4). A missing dump is the
    # legitimate pre-v96b case; a FAILED read is a 502 the strip renders as
    # its "checks did not run" degraded state.
    try:
        raw_dump = await store.load_json_artifact(kit_id, _ACROFORM_ARTIFACT)
        dump_data: Optional[dict] = raw_dump if isinstance(raw_dump, dict) else None
    except FormKitNotFound:
        dump_data = None
    except FormKitStoreError as exc:
        _log.error("editor_kit_lint_dump_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(
            status_code=502, detail="Unable to read the kit's PDF form data"
        ) from exc
    if meta is None and dump_data is None:
        raise HTTPException(status_code=404, detail=f"Kit {kit_id} not found")
    findings = lint_schema(schema, dump_data)
    out = [LintFindingOut(**f.as_dict()) for f in findings]
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_kit_schema_linted", kit_id=kit_id, role=role.role, actor=role.label(),
              has_dump=dump_data is not None,
              errors=error_count, warnings=warning_count)
    return LintResponse(
        findings=out, errorCount=error_count, warningCount=warning_count,
    )


@router.post("/kits/{kit_id}/repair", response_model=RepairResponse)
async def repair_editor_kit(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
) -> RepairResponse:
    """One-click Repair-all for a kit's stored draft (bd polyglot-pdf-zgln, P5.3b).

    Loads the kit's schema + its persisted AcroForm dump (bd v96b) and runs the
    SAME deterministic backend.services.schema_repair.repair() the CLI extraction
    pass runs, so the result equals CLI repair on the same input. The repaired
    schema is stored back; the response reports what changed (mirroring the CLI's
    _bakeoff.authoring.repair block) plus the POST-repair lint counts the editor
    re-renders.

    Author tier: repair MUTATES the stored schema (like extraction), so it needs
    the author code, not the polish-only editor code. RepairError (the draft
    references PDF widgets that do not exist -- repair cannot invent mappings) is
    a 422 CLIENT error naming the widgets, not a 500: a human must fix the
    hallucinated reference. A complete (published) kit is refused (409) -- repair
    would rewrite a live schema; revert to draft first, same as save.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    if _is_write_locked(meta):
        raise HTTPException(
            status_code=409,
            detail=f"{_lock_reason(meta)} (Repair rewrites the schema.)",
        )
    _require_edit_lock(meta, role)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema to repair"
        ) from exc
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    dump_data = await _load_kit_dump(store, kit_id)
    try:
        repaired, repairs = repair_schema(schema, dump_data)
    except RepairError as exc:
        # Hallucinated widgets: repair must NOT paper over them (a 500 would read
        # as a server bug; this is a fixable data defect the author must resolve).
        raise HTTPException(status_code=422, detail=str(exc)[:400]) from exc

    try:
        await store.put_schema(kit_id, repaired, schema_file)
    except FormKitStoreError as exc:
        raise HTTPException(
            status_code=502, detail="Repair succeeded but the schema could not be "
                                    "stored",
        ) from exc

    # Report shape mirrors the CLI's _repair_schema (extract_form.py): substantive
    # repairs split applied/dropped, plus the alias hit count; alias-hit-rate is
    # the meta entry, not a substantive repair.
    substantive = [r for r in repairs if r.get("action") != "alias-hit-rate"]
    applied = sum(1 for r in substantive if not r.get("error"))
    dropped = sum(1 for r in substantive if r.get("error"))

    # Re-lint the repaired schema (dump-aware) so the editor re-renders the
    # remaining findings -- the SAME schema_lint the promotion gate uses.
    findings = lint_schema(repaired, dump_data)
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_schema_repaired", kit_id=kit_id, role=role.role, actor=role.label(),
              applied=applied, dropped=dropped,
              errors_after=error_count, warnings_after=warning_count)
    return RepairResponse(
        applied=applied, dropped=dropped, aliasHits=alias_hit_count(repairs),
        repairs=repairs, errorCount=error_count, warningCount=warning_count,
    )


@router.post("/kits/{kit_id}/translate-options",
             response_model=TranslateOptionsResponse)
async def translate_editor_kit_options(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
    force: bool = False,
) -> TranslateOptionsResponse:
    """Bake option label_translations into a kit's stored draft, standalone
    (bd polyglot-pdf-2h9j) -- the decoupled counterpart of the extraction
    post-pass, for schemas that were extracted before translations existed (or
    with the translation checkbox off). Runs IN-PROCESS (it is just the text
    adapter, no subprocess): ONE batched pro-tier call per supported spoken
    language over the labels the kit lacks, fanned out under the canonical
    lowercase-name key. force=true retranslates everything and overwrites the
    canonical keys (the remedy after option labels were renamed).

    Author tier + draft-only (409 on complete), same write-gating as repair.
    503 when no Gemini auth is configured (same gate as hosted extraction).
    Per-language failures do not fail the request -- the partial result is
    stored and failedLanguages tells the author to re-run.
    """
    kit_id = _safe_kit_id(kit_id)
    settings = get_settings()
    # NOTE: provider availability is NOT pre-checked here. resolve_editor_text_ai
    # below owns it for BOTH providers -- a Gemini-only precheck would 503 a
    # perfectly working claude-cli local session (bd polyglot-pdf-cpiw).
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    if _is_write_locked(meta):
        raise HTTPException(
            status_code=409,
            detail=f"{_lock_reason(meta)} (The translation bake rewrites the "
                   "schema.)",
        )
    _require_edit_lock(meta, role)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema to translate"
        ) from exc
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    # Provider choice (Gemini hosted / claude-cli local) is resolved in ONE
    # place so local and hosted cannot drift -- bd polyglot-pdf-cpiw.
    try:
        text_ai, model = resolve_editor_text_ai(settings)
    except EditorTextAIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    languages = {n: c for n, c in SPOKEN_LANGUAGE_BCP47.items()
                 if n != "english"}
    report = await bake_label_translations(
        schema, text_ai, languages, only_missing=not force)
    flags = report.get("flags") or []

    if report["changed"] or flags:
        # Persist the bake report -- flags included -- in the SAME provenance
        # slot extraction's step 3f writes (bd polyglot-pdf-9djc): lint re-emits
        # the flags from there, so the ValidationPanel surfaces the translation
        # worklist on this and every later lint pass. Before this, the route
        # spent the verify credits and DISCARDED the findings (V3 review note).
        authoring = schema.setdefault("_bakeoff", {}).setdefault("authoring", {})
        authoring["option_translation"] = dict(report, model=model)
        try:
            await store.put_schema(kit_id, schema, schema_file)
        except FormKitStoreError as exc:
            raise HTTPException(
                status_code=502,
                detail="Translation succeeded but the schema could not be stored",
            ) from exc

    dump_data = await _load_kit_dump(store, kit_id)
    findings = lint_schema(schema, dump_data)
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_kit_options_translated", kit_id=kit_id, role=role.role, actor=role.label(),
              model=model, changed=report["changed"], force=force,
              failed_languages=report["failed_languages"],
              flag_count=len(flags),
              errors_after=error_count, warnings_after=warning_count)
    return TranslateOptionsResponse(
        changed=report["changed"], model=model,
        failedLanguages=report["failed_languages"],
        languages=report["languages"], flags=flags,
        errorCount=error_count, warningCount=warning_count,
    )


def _load_derive_sections():
    """Import scripts/authoring/derive_sections.py (bd 6cfu.3).

    The derivation lives with the authoring scripts, not the backend package
    (extraction runs it in-process at step 3e via the same sys.path shape).
    Pure Python + PyMuPDF -- both already backend runtime deps -- so unlike
    the LLM extractor there is no subprocess to manage."""
    root = _repo_root()
    for sub in (("scripts", "authoring"), ("scripts", "bakeoff")):
        p = str(root.joinpath(*sub))
        if p not in sys.path:
            sys.path.insert(0, p)
    import derive_sections  # noqa: PLC0415 (repo-layout import by design)
    return derive_sections


@router.post("/kits/{kit_id}/derive-divisions",
             response_model=DeriveDivisionsResponse)
async def derive_editor_kit_divisions(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
) -> DeriveDivisionsResponse:
    """Regenerate the kit's form divisions deterministically (bd 6cfu.3).

    Re-runs the SAME derivation extraction runs at step 3e
    (derive_sections.derive_and_apply) on the kit's STORED schema + its PDF:
    parts/sections are recomputed from the PDF (widget-name conventions ->
    printed headings -> page fallback) and every field's section_id is
    re-filed. DESTRUCTIVE to manual division edits by design -- the editor
    fronts this with a confirm dialog; field content is untouched.

    Author tier (it rewrites the stored schema, like extract/repair). A
    complete (published) kit is refused (409) -- revert to draft first, same
    as save/repair. A kit without its PDF cannot derive (409). A PDF the
    derivation cannot read (0 pages / corrupt) is a 422 data defect, not a
    500.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    if _is_write_locked(meta):
        raise HTTPException(
            status_code=409,
            detail=f"{_lock_reason(meta)} (Regenerating divisions rewrites the "
                   "schema.)",
        )
    _require_edit_lock(meta, role)
    schema_file, pdf_file = _resolve_meta_names(meta)
    if pdf_file not in files:
        raise HTTPException(
            status_code=409,
            detail=f"Kit has no {pdf_file} -- divisions are derived from the "
                   "form PDF",
        )
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema"
        ) from exc
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc
    try:
        pdf_bytes = await store.load_pdf_bytes(kit_id, pdf_file)
    except (FormKitNotFound, FormKitStoreError) as exc:
        raise HTTPException(status_code=502, detail="Unable to load the kit PDF") from exc

    derive_sections = _load_derive_sections()

    def _run() -> dict:
        # fitz needs a real path; the PDF lives in the store, not on disk.
        with tempfile.TemporaryDirectory() as td:
            pdf_path = os.path.join(td, "form.pdf")
            with open(pdf_path, "wb") as fh:
                fh.write(pdf_bytes)
            return derive_sections.derive_and_apply(schema, pdf_path)

    try:
        summary = await anyio.to_thread.run_sync(_run)
    except ValueError as exc:
        # 0-page/corrupt PDF (derive_for_pdf's friendly error): a fixable data
        # defect the author must resolve, not a server bug.
        raise HTTPException(status_code=422, detail=str(exc)[:400]) from exc

    # Keep the extraction-metadata division record truthful when present (the
    # CLI writes _bakeoff.authoring.division; a regenerate supersedes it).
    bakeoff = schema.get("_bakeoff")
    if isinstance(bakeoff, dict):
        authoring = bakeoff.get("authoring")
        if isinstance(authoring, dict):
            authoring["division"] = summary

    try:
        await store.put_schema(kit_id, schema, schema_file)
    except FormKitStoreError as exc:
        raise HTTPException(
            status_code=502,
            detail="Divisions derived but the schema could not be stored",
        ) from exc

    dump_data = await _load_kit_dump(store, kit_id)
    findings = lint_schema(schema, dump_data)
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_divisions_derived", kit_id=kit_id, role=role.role, actor=role.label(),
              strategy=summary["strategy"], sections=summary["sections"],
              to_review=len(summary["to_review_field_ids"]),
              errors_after=error_count, warnings_after=warning_count)
    return DeriveDivisionsResponse(
        strategy=summary["strategy"], parts=summary["parts"],
        sections=summary["sections"],
        toReviewSectionIds=summary["to_review_section_ids"],
        toReviewFieldIds=summary["to_review_field_ids"],
        notes=summary["notes"],
        errorCount=error_count, warningCount=warning_count,
    )


# Fields per model call for guidance regeneration. Mirrors the CLI default
# (scripts/authoring/enrich_instructions.py --chunk-size): the whole booklet
# rides every chunk, so a smaller chunk costs more calls, and a larger one
# risks a truncated response on a long form.
_GUIDANCE_CHUNK_SIZE = 12

# Instruction-booklet filenames vary by kit (w7-instructions.pdf, i-90instr.pdf,
# the editor upload's instructions.pdf), so match the same shapes
# enrich_instructions.find_booklet globs -- MOST specific first, and never the
# form itself.
_BOOKLET_PATTERNS = ("instructions.pdf", "*instructions*.pdf", "*instr*.pdf")


def _find_booklet_file(files, form_pdf: str = "form.pdf") -> Optional[str]:
    """The kit's instructions booklet filename, or None.

    `form_pdf` is the kit's OWN form (metadata-declared, so not always
    "form.pdf") and is excluded: a kit whose PDF happened to match one of the
    booklet globs would otherwise have its blank form fed to the enrichment
    engine as the grounding text.
    """
    names = [n for n in (files or []) if str(n).lower().endswith(".pdf")]
    for pattern in _BOOKLET_PATTERNS:
        for name in names:
            if name == form_pdf or name == "form.pdf":
                continue
            if fnmatch.fnmatch(name.lower(), pattern):
                return name
    return None


def _help_snapshot(schema: dict, field_id: str) -> tuple:
    """A field's guidance channels, for before/after comparison."""
    for f in schema.get("fields", []):
        if isinstance(f, dict) and f.get("id") == field_id:
            help_obj = f.get("help") if isinstance(f.get("help"), dict) else {}
            return tuple(
                help_obj.get(k) for k in ("instructions", "details",
                                          "format_hint")
            )
    return ()


def _load_enrich_instructions():
    """Import scripts/authoring/enrich_instructions.py (bd polyglot-pdf-cpiw).

    Same repo-layout import as _load_derive_sections: the authoring passes live
    with the scripts, not in the backend package, and the enrichment core
    (enrich_schema / apply_proposals) is pure Python calling the shared provider
    seam."""
    root = _repo_root()
    for sub in (("scripts", "authoring"), ("scripts", "bakeoff")):
        p = str(root.joinpath(*sub))
        if p not in sys.path:
            sys.path.insert(0, p)
    import enrich_instructions  # noqa: PLC0415 (repo-layout import by design)
    return enrich_instructions


def _guidance_model(settings) -> str:
    """The model for guidance regeneration.

    An explicit EDITOR_GUIDANCE_MODEL wins. Otherwise follow the editor's text
    provider, because the enrichment path dispatches on the MODEL NAME
    (llm_providers.resolve_json_runner: gemini-* -> Gemini, anything else ->
    the local claude CLI) -- so handing it "sonnet" is what routes it to the
    free local CLI, and a gemini-* name is what keeps hosted on Gemini."""
    explicit = (getattr(settings, "EDITOR_GUIDANCE_MODEL", "") or "").strip()
    if explicit:
        return explicit
    provider = (getattr(settings, "EDITOR_TEXT_PROVIDER", "") or "").strip().lower()
    if provider == "claude-cli":
        return getattr(settings, "EDITOR_CLAUDE_MODEL", "sonnet") or "sonnet"
    return settings.EXTRACTOR_MODEL


@router.post("/kits/{kit_id}/regenerate-guidance",
             response_model=RegenerateGuidanceResponse)
async def regenerate_editor_kit_guidance(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
    body: RegenerateGuidanceBody | None = None,
) -> RegenerateGuidanceResponse:
    """Re-author field guidance from the kit's instruction booklet.

    THE MISSING HALF OF THE STALENESS GATE (bd anim / bd polyglot-pdf-cpiw).
    When a reviewer renames a field, lint flags its guidance as possibly stale
    and offers two ways out: acknowledge it still reads correctly (free), or
    re-author it (costly). Only "acknowledge" existed, so the costly path meant
    hand-copying prose out of the IRS/USCIS instructions booklet -- exactly the
    editor time this is meant to save.

    Scope: `fieldIds` limits the rewrite to those fields (the natural call from
    the staleness banner); omitted means every askable field. Fields whose
    guidance a HUMAN edited are never clobbered -- apply_proposals compares
    per-channel hashes against provenance and skips anything hand-owned.

    A successful rewrite re-stamps identity_sha1, which is what CLEARS the
    staleness flag for those fields.

    Author tier (it spends model tokens and rewrites the stored schema) and
    draft-only (409 on complete), the same write-gating as repair/translate.
    Needs an instructions booklet in the kit dir; without one there is nothing
    to ground the guidance in, so it 409s rather than inventing prose.
    """
    kit_id = _safe_kit_id(kit_id)
    # SERIALIZED per instance (bd polyglot-pdf-gnb0). The lock is taken BEFORE
    # the schema is loaded, so a queued request re-reads the store and sees the
    # previous run's written schema -- taking it any later would let both
    # requests mutate the same pre-lock snapshot and still lose one write. It
    # spans the whole read -> enrich -> apply -> put_schema window; the model
    # call inside is minutes long, so a second author's request waits (Cloud
    # Run's --timeout=3600 covers it), exactly like the extract route.
    async with _get_guidance_lock():
        return await _regenerate_guidance_locked(kit_id, role, body)


async def _regenerate_guidance_locked(
    kit_id: str,
    role: EditorActor,
    body: RegenerateGuidanceBody | None,
) -> RegenerateGuidanceResponse:
    """The regenerate-guidance critical section (see the caller's lock note).

    Split out ONLY so the lock wraps one call rather than re-indenting the
    whole body; every behavior here is unchanged from when it lived inline.
    `kit_id` arrives already normalized by _safe_kit_id.
    """
    settings = get_settings()
    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    if _is_write_locked(meta):
        raise HTTPException(
            status_code=409,
            detail=f"{_lock_reason(meta)} (Regenerating guidance rewrites the "
                   "schema.)",
        )
    _require_edit_lock(meta, role)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema"
        ) from exc
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    # The booklet is the GROUNDING for every proposal -- the enrichment prompt
    # quotes it and a contiguity repairer drops anything not verbatim from it.
    # No booklet, no honest guidance.
    booklet_file = _find_booklet_file(files, _pdf)
    if not booklet_file:
        raise HTTPException(
            status_code=409,
            detail="This form has no instructions booklet in its kit folder, "
                   "so guidance cannot be regenerated from source. Add the "
                   "official instructions PDF (e.g. w7-instructions.pdf) to "
                   "the kit and try again.",
        )
    try:
        booklet_bytes = await store.load_pdf_bytes(kit_id, booklet_file)
    except (FormKitNotFound, FormKitStoreError) as exc:
        raise HTTPException(
            status_code=502, detail="Unable to load the instructions booklet",
        ) from exc

    enrich = _load_enrich_instructions()
    model = _guidance_model(settings)
    requested = list(body.fieldIds) if body and body.fieldIds else []

    # Restrict the rewrite to the requested fields by enriching a SHALLOW COPY
    # holding only those fields. The proposals come back keyed by field id, so
    # they apply cleanly to the real schema afterwards.
    target = schema
    if requested:
        wanted = set(requested)
        target = dict(schema)
        target["fields"] = [f for f in schema.get("fields", [])
                            if isinstance(f, dict) and f.get("id") in wanted]
        if not target["fields"]:
            raise HTTPException(
                status_code=422,
                detail="None of the requested field ids exist in this form",
            )

    form_name = ((schema.get("form_metadata") or {}).get("title") or kit_id)

    def _run() -> tuple[dict, str, list]:
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, booklet_file)
            with open(path, "wb") as fh:
                fh.write(booklet_bytes)
            text = enrich.booklet_text(path)
        result = enrich.enrich_schema(
            target, text, form_name, model, _GUIDANCE_CHUNK_SIZE)
        # NEVER write unverified guidance. apply_proposals stamps
        # source="llm-verified", and every other caller (the CLI --write path
        # and the extraction pipeline) earns that label by running the judge +
        # bounded rectify first. This is legal-form prose read aloud to
        # applicants; skipping the judge here would put unreviewed model text
        # into a stored kit under a "verified" label. verify_and_rectify
        # MUTATES proposals per the KEEP rule and fails SAFE (a judge outage
        # empties the proposals rather than passing them through).
        #
        # The judge runs on the SAME provider as the author pass. Its default
        # (GUIDANCE_JUDGE_MODEL, gemini-2.5-flash) dispatches by model name, so
        # leaving it unset would send the author pass to the free local CLI and
        # the judge to metered Vertex -- spending money in the one mode the
        # maintainer directive says must not, and hard-failing on a machine with
        # no ADC (which then blanks every proposal via the fail-safe and returns
        # a success-shaped no-op).
        flags = enrich.verify_and_rectify(
            target, result.get("proposals") or {}, text, form_name, model,
            judge_model=model)
        return result, text, flags

    try:
        result, booklet, verify_flags = await anyio.to_thread.run_sync(_run)
    except Exception as exc:  # noqa: BLE001
        # A model/transport failure is not a server bug -- report it so the
        # editor can retry, exactly like the translate path's failed languages.
        _log.error("editor_guidance_regen_failed", kit_id=kit_id,
                   exc_type=type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail=f"Guidance regeneration failed ({type(exc).__name__}). "
                   "Nothing was changed; try again.",
        ) from exc

    proposals = result.get("proposals") or {}

    # No usable CONTENT came back -> do not write, and say so. Two ways to get
    # here, and an empty-dict check catches only the first:
    #   - enrich_schema filters to ASKABLE fields, so a fieldIds list of only
    #     read_only/signature fields yields zero chunks and no entries at all;
    #   - verify_and_rectify fails SAFE on a judge outage by blanking each
    #     entry to {} while KEEPING its key, so `fields` stays truthy.
    # Either way, falling through re-stamps the bake block and returns a
    # success the reviewer will read as "the guidance was re-authored".
    if not any(
        isinstance(e, dict)
        and any((e.get(k) or "").strip()
                for k in ("instructions", "details", "format_hint"))
        for e in (proposals.get("fields") or {}).values()
    ):
        _log.info("editor_guidance_regen_no_proposals", kit_id=kit_id,
                  requested=len(requested))
        dump_data = await _load_kit_dump(store, kit_id)
        findings = lint_schema(schema, dump_data)
        return RegenerateGuidanceResponse(
            regenerated=[], skipped=sorted(requested), model=model,
            booklet=booklet_file,
            errorCount=sum(1 for f in findings if f.severity == SEVERITY_ERROR),
            warningCount=sum(
                1 for f in findings if f.severity == SEVERITY_WARNING),
        )

    # A field-scoped rewrite must not touch FORM-level prose. enrich_schema
    # asks for form_details in every chunk (each chunk sees the whole booklet),
    # and apply_proposals writes it unconditionally -- so rewriting one field
    # would replace the kit's whole eligibility/where-to-file block with
    # whatever that one chunk happened to emit. Drop it when scoped.
    if requested:
        proposals = dict(proposals)
        proposals["form_details"] = ""

    # apply_proposals REPLACES the whole instructions_enrich block, so the
    # prior flags + judge_model must be carried through or a rewrite silently
    # wipes the reviewer's guidance worklist (schema_lint re-emits those flags
    # as findings) and blanks the record of which judge verified the kit.
    prior = (((schema.get("_bakeoff") or {}).get("authoring") or {})
             .get("instructions_enrich") or {})
    prior_flags = prior.get("flags")
    prior_judge = prior.get("judge_model")
    # Snapshot BEFORE the apply so `regenerated` can report what actually
    # changed (see the comment where it is computed).
    help_before = {
        f["id"]: _help_snapshot(schema, f["id"])
        for f in schema.get("fields", [])
        if isinstance(f, dict) and isinstance(f.get("id"), str)
    }
    merged_flags = (list(prior_flags) if isinstance(prior_flags, list) else [])
    merged_flags += list(verify_flags or [])
    summary = enrich.apply_proposals(
        schema, proposals, booklet,
        flags=merged_flags,
        model=model,
        judge_model=prior_judge if isinstance(prior_judge, str) else "",
    )
    # Report what was actually WRITTEN, not what was proposed. apply_proposals
    # deliberately SKIPS any field whose guidance a human edited (its
    # per-channel hashes no longer match provenance), so a proposal-derived
    # list would tell the reviewer their hand-written text was overwritten
    # when the route's whole contract is that it was not. Compared against the
    # pre-call snapshot, so this tracks apply_proposals' real behavior rather
    # than re-implementing its skip rule.
    schema_ids = {f.get("id") for f in schema.get("fields", [])
                  if isinstance(f, dict)}
    # An UNSCOPED run only ever offered the model the ASKABLE fields, so
    # read_only/signature fields were never candidates and must not be reported
    # as "skipped" -- that reads as a failure to rewrite something we tried to.
    askable_ids = {
        f.get("id") for f in enrich.askable_fields(schema)
        if isinstance(f, dict)
    }
    scope = (set(requested) & schema_ids) if requested else askable_ids
    regenerated = sorted(
        fid for fid in scope
        if _help_snapshot(schema, fid) != help_before.get(fid)
    )
    skipped = sorted(scope - set(regenerated))

    try:
        await store.put_schema(kit_id, schema, schema_file)
    except FormKitStoreError as exc:
        raise HTTPException(
            status_code=502,
            detail="Guidance was regenerated but the schema could not be "
                   "stored",
        ) from exc

    dump_data = await _load_kit_dump(store, kit_id)
    findings = lint_schema(schema, dump_data)
    error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    _log.info("editor_guidance_regenerated", kit_id=kit_id, role=role.role, actor=role.label(),
              model=model, requested=len(requested),
              written=summary.get("written"),
              skipped_human=summary.get("skipped_human"),
              errors_after=error_count, warnings_after=warning_count)
    return RegenerateGuidanceResponse(
        regenerated=regenerated, skipped=skipped, model=model,
        booklet=booklet_file,
        errorCount=error_count, warningCount=warning_count,
    )


@router.get("/kits/{kit_id}/unclaimed-widgets",
            response_model=UnclaimedWidgetsResponse)
async def get_unclaimed_widgets(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
) -> UnclaimedWidgetsResponse:
    """The kit's PDF button widgets that no field/option claims (bd nivy, P5.3c).

    Powers the author-tier "Add from PDF widgets" picker: when the extractor
    missed a checkbox/radio box, the box exists in the persisted AcroForm dump
    (acroform.json, bd v96b) but nothing in the schema claims it. This returns
    those unclaimed button widgets so the author can add one to a group.

    Author tier (it feeds an edit that adds a PDF-mapped option -- an author-only
    capability, matching the per-option pdf_field_name editor). A kit with no
    persisted dump (pre-v96b) returns an empty list -- the picker shows nothing.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    schema_file, _pdf = _resolve_meta_names(meta)
    try:
        schema = await store.load_schema(kit_id, schema_file)
    except FormKitNotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"Kit {kit_id} has no schema"
        ) from exc
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to load schema") from exc

    dump = await _load_kit_dump(store, kit_id)
    widgets = [UnclaimedWidget(**w) for w in unclaimed_button_widgets(schema, dump)]
    _log.info("editor_unclaimed_widgets", kit_id=kit_id, role=role.role, actor=role.label(),
              count=len(widgets), has_dump=dump is not None)
    return UnclaimedWidgetsResponse(widgets=widgets)


async def _sweep_drifted_translations(
    store,
    kit_id: str,
    schema: dict,
    schema_file: str,
) -> tuple[int, Optional[str]]:
    """Fill every MISSING translation in `schema` and gate on full coverage
    (bd polyglot-pdf-783r), for the Mark-complete drift sweep.

    Mutates `schema` in place (so the caller's later validate/lint gates see the
    swept schema) and persists it whenever anything changed. Uses the SAME bake
    as /translate-options with only_missing=True -- so it never re-litigates a
    non-drifted translation -- plus per-language 1s/5s retry backoff
    (TRANSLATE_RETRY_DELAYS). Returns (entries_freshly_baked, model_or_None).

    Raises HTTPException to REFUSE completion when:
      - Gemini auth is not configured (503; the sweep cannot run -- a
        maintainer/config issue, so the message points the editor at the
        maintainer);
      - after the sweep some supported language is still incomplete (409 with
        the "N of M" progress message; a re-press retries only the gaps).
    """
    settings = get_settings()
    # Provider choice (Gemini hosted / claude-cli local) is resolved in ONE
    # place so local and hosted cannot drift -- bd polyglot-pdf-cpiw.
    try:
        text_ai, model = resolve_editor_text_ai(settings)
    except EditorTextAIUnavailable as exc:
        # A config/deployment issue, not something the editor can fix -- point
        # them at the maintainer and block (maintainer 2026-07-26).
        raise HTTPException(
            status_code=503,
            detail=f"{exc} This form cannot be checked for translation drift "
                   "before completion. Please contact the maintainer at "
                   "josh@caellwynai.com.",
        ) from exc

    languages = {n: c for n, c in SPOKEN_LANGUAGE_BCP47.items()
                 if n != "english"}
    report = await bake_label_translations(
        schema, text_ai, languages, only_missing=True,
        attempt_delays=TRANSLATE_RETRY_DELAYS,
    )
    # Entries freshly baked across every class + language (for the editor note).
    retranslated = sum(
        e.get("options_updated", 0) + e.get("fields_updated", 0)
        + e.get("sections_updated", 0)
        for e in report.get("languages", {}).values()
    )
    flags = report.get("flags") or []
    if report.get("changed") or flags:
        # Persist into the SAME provenance slot the extraction post-pass and
        # /translate-options write, so a later lint re-emits the flags -- and so
        # the freshly baked translations survive even if a LATER gate
        # (validate/lint) blocks this completion (the next press's sweep then
        # no-ops over them).
        authoring = schema.setdefault("_bakeoff", {}).setdefault("authoring", {})
        authoring["option_translation"] = dict(report, model=model)
        try:
            await store.put_schema(kit_id, schema, schema_file)
        except FormKitStoreError as exc:
            raise HTTPException(
                status_code=502,
                detail="Re-translation succeeded but the schema could not be "
                       "stored",
            ) from exc

    summary = translation_coverage_summary(schema)
    if not summary.complete:
        _log.info(
            "editor_status_translation_incomplete", kit_id=kit_id,
            covered=summary.covered_languages, total=summary.total_languages,
            incomplete=summary.incomplete_languages,
            failed_languages=report.get("failed_languages"),
        )
        raise HTTPException(status_code=409, detail=summary.message())
    return retranslated, (model if retranslated else None)


@router.post("/kits/{kit_id}/status", response_model=KitStatusResponse)
async def set_editor_kit_status(
    kit_id: str,
    body: KitStatusBody,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> KitStatusResponse:
    """Set a kit's status (draft | submitted | complete | unpublished),
    preserving other metadata keys.

    THE ROLE DEPENDS ON THE TRANSITION, not the route (bd polyglot-pdf-hqztg).
    An editor submits for review; an author publishes. Editors are
    subcontractors, so marking a form ready must not release it -- and an
    editor cannot reach back into a live form at all.

    `complete` is the PUBLISH gate: the deploy ships only complete kits to the
    voice app, so that transition requires a schema that exists AND validates
    against the canonical FormSchema -- a broken schema surfaces here, to the
    person who can fix it, not later in the voice app. The gate applies to
    EVERY route into `complete`, including a retired kit returning to service.

    `unpublished` retires a superseded revision (bd polyglot-pdf-6dz0): hidden
    from clients like a draft, but WRITE-LOCKED like complete, because its
    schema is what earlier confirmation records were confirmed against. Two
    transition rules follow: only a live kit can be unpublished, and an
    unpublished kit can NEVER go back to draft (draft is editable, which would
    let the bytes an audit record names be rewritten in place) -- it returns
    only through the publish gate. Reverting a COMPLETE kit to draft stays
    unconditional; retiring EITHER way archives the revision first.

    `replaces_kit_id` retires another live kit for the same form as part of
    this publish, so a new edition onboarded as its own kit does not leave two
    live entries. The outgoing kit is archived early but flipped only after the
    incoming kit is live: the failure mode is two live entries, never zero.

    DRIFT SWEEP (bd polyglot-pdf-783r): before the validate/lint gates, a
    completion re-translates every spoken-name / option-label / section-label
    whose translation is missing -- which, because editing an English string in
    the editor DROPS its baked translations, is exactly the set that drifted
    during human review (plus anything never translated). The sweep runs
    server-side as a STEP of the editor-authorized completion (so it needs no
    author role -- an editor, who cannot call /translate-options, can still fix
    drift), retries each language with backoff, and REFUSES completion until
    every supported language is fully covered (the "N of M" message). It is
    idempotent: a re-press retries only the still-missing languages.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    schema_file, pdf_file = _resolve_meta_names(meta)
    retranslated = 0
    translation_model: Optional[str] = None

    current_status = _status_of(meta)

    # THE EDITING LOCK GUARDS THIS WHOLE ROUTE, hoisted here so it DOMINATES
    # every write below rather than sitting between them (bd polyglot-pdf-hqztg,
    # Opus fresh-eyes). This route has TWO put_schema calls -- the rejection
    # clear and the author-version persistence -- and the guard used to sit
    # after the first. An editor reopening their own submission therefore
    # rewrote the schema while an AUTHOR held the lock, which is exactly the
    # "they approve something they never saw" case the lock exists to prevent,
    # and worse: it also flipped the kit out of write-locked `submitted`, so
    # every later editor write was permitted too. Reproduced end to end before
    # this fix. It also now covers the archive hook below.
    _require_edit_lock(meta, role)

    # An UNPUBLISHED kit may never walk back to draft (bd polyglot-pdf-6dz0).
    # Draft is editable, and this kit's schema is what earlier confirmation
    # records were confirmed against -- letting it become editable would make
    # the archive pointless, since the bytes an audit record names could then
    # be rewritten in place. It returns to service only through the full
    # publish gate, which archives first.
    if body.status == "draft" and current_status == "unpublished":
        raise HTTPException(
            status_code=409,
            detail="This form is unpublished (a superseded revision) and "
                   "cannot be reverted to draft -- its schema is what earlier "
                   "confirmation records were confirmed against. Publish it "
                   "again to put it back in service; that archives the retired "
                   "copy first.",
        )

    # --- the role split, PER TRANSITION (bd polyglot-pdf-hqztg) -------------
    #
    # One route carries several transitions, so the role check belongs HERE
    # rather than on the route -- the s18 plan's insight, kept; only the
    # mapping changed (maintainer decision 2026-08-11, which amended epic
    # polyglot-pdf-4qul's rubric criterion 3):
    #
    #   draft -> submitted     editor-allowed  ("I believe this is ready")
    #   submitted -> complete  AUTHOR-ONLY     (releasing is accountable)
    #   * -> draft             editor-allowed  (reopening one's own work)
    #   complete -> anything   author-only     (already covered below)
    #
    # Editors are subcontractors. Marking a form ready must not release it.
    if body.status == "complete" and not role.is_author:
        raise HTTPException(
            status_code=403,
            detail=(
                "Publishing is an author action. Submit this form for review "
                "instead -- an author checks it and publishes it."
            ),
        )

    # An editor may not reach back into a LIVE form AT ALL -- neither to reopen
    # it nor to retire it. Both destinations, not just draft: unpublishing takes
    # a form away from every client, and it is a ONE-WAY door for an editor
    # (revert-to-draft then 409s under the 6dz0 immutability rule, and
    # republishing 403s under the rule above), so a subcontractor could pull a
    # live form and be unable to restore it. My first version checked only
    # `draft` while the comment claimed "complete -> anything" was covered --
    # a false claim a later reader would trust (Opus fresh-eyes round 2,
    # reproduced end to end). Reverting one's own SUBMITTED work stays allowed.
    if (
        body.status in ("draft", "unpublished")
        and current_status in ("complete", "unpublished")
        and not role.is_author
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "This form is published, so only an author can reopen or retire "
                "it. Ask an author."
            ),
        )

    # Submitting is only meaningful from draft: a submitted kit is already
    # awaiting review, and a published one would be a downgrade nobody asked
    # for (reopen it deliberately instead).
    if body.status == "submitted" and current_status != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Only a draft can be submitted for review (this one is "
                   f"{current_status}).",
        )

    # Publishing goes through review: an author publishes what an editor
    # submitted, or their own draft. There is no path from a RETIRED kit
    # straight to complete that skips the gate -- that stays the republish
    # route, which runs every check (bd polyglot-pdf-6dz0/xzw5).

    # Unpublishing is only meaningful for a kit that is actually live.
    if body.status == "unpublished" and current_status != "complete":
        raise HTTPException(
            status_code=409,
            detail=f"Only a published form can be unpublished (this one is "
                   f"{current_status}).",
        )

    # Retiring a PUBLISHED revision -- to draft for editing, or to unpublished
    # for good -- is the last moment its bytes exist unaltered: every editing
    # route refuses to write while it is locked. Archive them first (bd
    # polyglot-pdf-w3zw) so a confirmation record naming that revision can
    # still be resolved to the exact schema it was confirmed against.
    if body.status in ("draft", "unpublished") and current_status == "complete":
        await _archive_published_revision(store, kit_id, meta)

    # CROSS-KIT SUPERSEDE validation (bd polyglot-pdf-asr2a): these four
    # checks are all cheap and purely LOCAL -- they depend on nothing the
    # publish gate below computes -- so they run BEFORE the metered
    # per-language translation drift sweep. Validating a bad supersede
    # target only AFTER paying for that sweep burned real model calls on a
    # request that was always going to be refused; reject for free first,
    # same "cheap gates before the pro-tier sweep" principle
    # _sweep_drifted_translations' own call site already follows. The
    # ARCHIVE WRITE for the outgoing kit stays deferred to its original spot
    # (after every gate for the incoming kit has passed) -- only the
    # read-only validation moved earlier.
    superseded_kit: Optional[str] = None
    superseded_meta: Optional[dict] = None
    if body.status == "complete" and body.replaces_kit_id:
        superseded_kit = _safe_kit_id(body.replaces_kit_id)
        if superseded_kit == kit_id:
            raise HTTPException(
                status_code=409,
                detail="A form cannot replace itself -- republishing the same "
                       "kit already replaces its own catalogue entry.",
            )
        superseded_meta, _old_files = await _load_meta_or_404(store, superseded_kit)
        if _status_of(superseded_meta) != "complete":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot replace {superseded_kit}: it is not published "
                       f"(status {_status_of(superseded_meta)}), so there is "
                       "nothing to retire.",
            )


    # REJECTION clears the author version (maintainer decision 2026-08-11). A
    # submitted kit was never live, so no confirmation record names its version
    # -- there is nothing to protect, and the next publish asks for one again.
    #
    # Scoped to submitted -> draft, NOT to every revert: reopening a PUBLISHED
    # kit must KEEP its version, because records DO name that one. Clearing it
    # there would let the next publish invent a different marker for a revision
    # clients already confirmed against, which is precisely the re-pointing the
    # xzw5 immutability lock exists to prevent. This keeps the lock's meaning
    # exact -- it protects PUBLISHED versions only.
    version_cleared = False
    if body.status == "draft" and current_status == "submitted":
        try:
            schema = await store.load_schema(kit_id, schema_file)
        except (FormKitNotFound, FormKitStoreError):
            schema = None
        meta_block = (schema or {}).get("form_metadata")
        if isinstance(meta_block, dict) and meta_block.get("author_version"):
            meta_block = {k: v for k, v in meta_block.items() if k != "author_version"}
            schema = {**schema, "form_metadata": meta_block}
            try:
                await store.put_schema(kit_id, schema, schema_file)
                version_cleared = True
            except FormKitStoreError as exc:
                # Best-effort, like the archive hook above: failing to clear a
                # version must not strand a kit in submitted, which would leave
                # the editor unable to reopen their own work.
                _log.warning("editor_version_clear_failed", kit_id=kit_id, error=str(exc))
    if version_cleared:
        _log.info("editor_rejected_version_cleared", kit_id=kit_id, role=role.role, actor=role.label())

    # STRUCTURAL GATES apply to BOTH promotions. Submitting used to run
    # NOTHING: an editor could freeze a kit around a garbage, PDF-less,
    # non-v2 schema, filling an author's review queue with kits that could
    # never publish -- and `submitted` is write-locked, so the author had to
    # manually reject each one. My own UI comment claimed "an editor's
    # SUBMIT runs the same readiness/lint gate"; it did not (Opus fresh-eyes
    # round 4, reproduced live). Cheap refusals belong at the point the work
    # leaves the editor's hands.
    if body.status in ("submitted", "complete"):
        # These gates now front BOTH promotions, so the refusals must name the
        # action the caller actually attempted. Telling an editor a form
        # "cannot be marked complete" named an action their tier is 403'd from
        # -- and the editor is this gate's main audience, since the strip
        # deliberately surfaces submit refusals to them (round 9).
        action = ("submitted for review" if body.status == "submitted"
                  else "marked complete")
        gerund = ("submitting it for review" if body.status == "submitted"
                  else "marking it complete")
        # The voice app serves BOTH the schema and the PDF of a complete kit;
        # the deploy manifest falls back to a conventional pdf name when none
        # exists, so promoting a PDF-less kit would ship a form whose PDF read
        # 404s in the voice app (Codex P1 r2, PR #279).
        if pdf_file not in files:
            raise HTTPException(
                status_code=409,
                detail=f"Kit has no {pdf_file} -- it needs its form PDF "
                       f"(the voice app serves it) before being {action}",
            )
        try:
            schema = await store.load_schema(kit_id, schema_file)
        except FormKitNotFound as exc:
            raise HTTPException(
                status_code=409,
                detail="Kit has no schema yet -- extract and save one before "
                       f"{gerund}",
            ) from exc
        except FormKitStoreError as exc:
            raise HTTPException(
                status_code=502, detail="Unable to load schema"
            ) from exc

        try:
            parsed = FormSchema.model_validate(schema)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Schema does not validate against the form contract, so "
                       f"it cannot be {action}: {str(exc)[:400]}",
            ) from exc
        # Pydantic v2 does not run field validators for an OMITTED default, so
        # the model's "extraction_info required for PDF forms" rule never fires
        # on an absent value -- a PDF schema with no extraction metadata would
        # validate. Enforce the documented contract explicitly at the publish
        # gate (Codex P1 r2, PR #279); the extraction pipeline emits it, so a
        # legitimate kit is unaffected.
        if parsed.source == FormSource.PDF and parsed.extraction_info is None:
            raise HTTPException(
                status_code=422,
                detail="Schema is missing extraction_info (required for PDF "
                       f"forms), so it cannot be {action}",
            )
        # v2-only gate (bd h76m.16, P6.2 flip): schema v2 is the only shape a
        # complete kit may carry. The model IGNORES unknown keys (extra="ignore"),
        # so a v2-shaped-but-unstamped schema still carrying a removed trigger-side
        # key (controls_fields / conditional_fields) would slip past both the model
        # AND the is_v2-gated lint below; requiring the stamp here closes that
        # (bd polyglot-pdf-t96a). The extraction + migration pipelines both stamp
        # v2, so a legitimate kit is unaffected.
        if str(schema.get("schema_version")) != vocab.SCHEMA_VERSION_V2:
            raise HTTPException(
                status_code=422,
                detail="Schema is not v2 (schema_version must be \"2\"); migrate "
                       f"it before {gerund}",
            )
        # Lint gate (bd h76m.5, P2.1): zero lint ERRORs to promote. Pydantic
        # above enforces the wire contract; lint catches the class of defect
        # that PARSES but misbehaves (duplicate option values, unresolved
        # conditional references, invented operators on a v1-stamped draft).
        # This is one half of the two-gate seam: a stored-with-issues draft
        # (P5.3) stays un-promotable until repaired. WARNINGs never block.
        # The AcroForm dump is now a per-kit artifact (bd v96b), so pass it when
        # present -- this closes the dump-only widget-claim rule at the promotion
        # gate too (a missing dump degrades to the dump-less rules, never blocks).
        dump_data = await _load_kit_dump(store, kit_id)
        gate_findings = lint_schema(schema, dump_data)
        lint_errors = [f for f in gate_findings if f.severity == SEVERITY_ERROR]
        if lint_errors:
            # Cap the finding list BEFORE appending the "and N more" tail so
            # a long list can never truncate away the count of what was
            # elided. Each segment is ALSO capped at 400 chars before
            # joining: a single finding whose message embeds a very long
            # option value (e.g. a 10KB string) would otherwise eat the
            # whole budget on its own, hiding later findings within the
            # first 8 (bd polyglot-pdf-tmby nit 1). 400 (was 200): the
            # bd-xfdb copy pass moved every message's remedy clause to the
            # END, and the old cap systematically cut exactly that clause
            # at the one gate where the reviewer is actively blocked. The
            # outer cap is 8 x 400 + 7 x len("; ") = 3214 -- sized so the
            # per-segment cap is ALWAYS the binding constraint (a smaller
            # outer cap re-cuts the 8th finding's remedy; Opus outer
            # review, both points measured).
            shown = "; ".join(
                f"[{f.rule}] {f.path}: {f.message}"[:400] for f in lint_errors[:8]
            )[:3214]
            more = len(lint_errors) - 8
            if more > 0:
                shown += f"; ... and {more} more"
            raise HTTPException(
                status_code=409,
                detail=f"Schema has {len(lint_errors)} lint error(s), so it "
                       f"cannot be marked complete: {shown}",
            )

        # Drift sweep (bd polyglot-pdf-783r): fill every MISSING translation
        # (the drifted-during-review set + any never-translated), persist, then
        # gate on full coverage. Runs LAST, AFTER the cheap structural gates
        # (validate / extraction_info / v2-stamp / lint) -- those reject a bad
        # schema for FREE, so a schema that will be refused anyway never pays for
        # the pro-tier sweep (fresh-eyes cost finding, bd 783r). The sweep does
        # not affect any earlier gate: translations are additive metadata that
        # leave schema validity, extraction_info, the v2 stamp, and every lint
        # rule (option values / conditions / widgets) untouched.

        # --- author version gate (bd polyglot-pdf-xzw5) ---------------------
        # Runs AFTER validate/extraction_info/v2-stamp/lint deliberately. Those
        # gates report what is WRONG with the schema; this one asks the author
        # for something extra. Running it first masked them -- an author with a
        # structurally broken schema was told to supply a version instead of
        # being shown the actual defect (caught by the neighbouring suite's
        # test_mark_complete_validates_against_form_contract).
        # Version handling and the sweep are PUBLISH-only from here.

    if body.status == "complete":
        meta_block = schema.get("form_metadata")
        meta_block = meta_block if isinstance(meta_block, dict) else {}
        existing_edition = meta_block.get("edition_date")
        has_edition = isinstance(existing_edition, str) and existing_edition.strip()
        existing_author_version = meta_block.get("author_version")
        has_existing_version = (
            isinstance(existing_author_version, str)
            and existing_author_version.strip()
        )
        # Normalize ONCE, before any comparison or branch. Comparing a RAW
        # supplied value against a NORMALIZED stored one made a legitimate
        # republish look like a change: stored "2026-01-01" vs supplied
        # "v2026-01-01" are the same revision after this route's own rule, but
        # 409'd as if they were different (Opus fresh-eyes, reproduced live).
        supplied_version = _normalize_author_version(body.author_version)
        version_to_persist: Optional[str] = None

        if not has_edition:
            # LOCKED once set: author_version is what earlier confirmation
            # records name, so changing it would silently re-point them at a
            # revision those clients never saw -- the same hazard the retired-
            # kit write-lock exists to prevent (maintainer decision, 2026-08-08).
            # A republish of an already-versioned kit keeps the original.
            #
            # Gated on HAVING BEEN PUBLISHED, not on the value merely existing.
            # The version is written before the translation sweep, and that
            # sweep routinely refuses (a partially-translated kit 409s with
            # "N of M translations complete") -- leaving the kit in DRAFT with a
            # version on disk. Locking on presence alone made that failed
            # attempt permanent: the author's retry with a corrected version was
            # refused, citing confirmation records that do not exist, on a kit
            # the route explicitly expects them to re-press. A draft has no
            # records to protect, so its version stays editable.
            was_published = current_status in _PUBLISHED_STATUSES
            if has_existing_version and was_published:
                # Locked: only a REPUBLISH of the same version is allowed.
                if supplied_version and supplied_version != _normalize_author_version(
                    existing_author_version
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f'This kit was already published as version '
                            f'"{existing_author_version.strip()}", and that version is '
                            f"what its existing confirmation records name. Changing it "
                            f"would re-point them at a revision those clients never saw. "
                            f"Publish a new kit for a new revision instead."
                        ),
                    )
            elif current_status == "complete" and supplied_version:
                # A kit that is CURRENTLY LIVE with no version: accepting one
                # would rewrite the exact bytes its existing confirmation
                # records were confirmed against, in place and with no archive
                # -- which is what the write-lock on every other schema-writing
                # route exists to prevent (Opus fresh-eyes found this write was
                # the one exception in the file). A legacy kit gets its version
                # by publishing a NEW revision, the same route any other
                # schema change takes.
                #
                # Scoped to `complete`, NOT to write-locked generally. An
                # UNPUBLISHED kit is retired -- serving nobody -- and republish
                # is its one documented route back into service, which archives
                # the outgoing revision first. Refusing it here bricked exactly
                # the kit class this bead exists to serve: revert-to-draft is a
                # hard 409 for a retired kit (bd polyglot-pdf-6dz0), so every
                # exit was closed AND this message named one the API forbids
                # (Opus fresh-eyes round 3, reproduced).
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f'"{kit_id}" is already published without a version. Adding '
                        f"one now would rewrite the schema its existing confirmation "
                        f"records were confirmed against. Revert it to draft and "
                        f"publish again to give this revision a version."
                    ),
                )
            elif has_existing_version and not supplied_version:
                # A DRAFT carrying a version from an earlier failed publish, being
                # re-pressed with nothing new: keep what is already there rather
                # than demanding the author retype it. (Refusing here would make
                # the retry path the sweep invites impossible to walk.)
                pass
            elif not supplied_version:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "AUTHOR_VERSION_REQUIRED: this form has no government "
                        "edition date, so it needs an author version to identify "
                        "which revision a client confirmed against -- otherwise its "
                        "records fall back to an unreadable content fingerprint. "
                        'Supply author_version (e.g. "2026-08-07").'
                    ),
                )
            else:
                # Already normalized above. Persist into the schema, which is
                # what the client is served and what the voice path reads the
                # marker from.
                meta_block = dict(meta_block)
                meta_block["author_version"] = supplied_version
                schema = dict(schema)
                schema["form_metadata"] = meta_block
                version_to_persist = supplied_version


        # Persist a newly-supplied author version (bd polyglot-pdf-xzw5) AFTER
        # the free gates and BEFORE the sweep. This route otherwise never writes
        # the schema, so without this the normalized value would be validated
        # and then thrown away -- the marker has to be IN the served schema,
        # because that is where the voice path reads it from. Only runs when the
        # gate above actually set it (no edition_date, no prior version).
        # This route DOES write the schema (the author-version persistence
        # below), so it honours the editing lock like every other writer.
        # Reachable only author-to-author: publishing is already author-only,
        # so an editor cannot get here -- but a second author publishing a kit
        # the first is reviewing is exactly the collision the lock exists for.
        if version_to_persist is not None:
            try:
                await store.put_schema(kit_id, schema, schema_file)
            except FormKitStoreError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Unable to save the author version",
                ) from exc

        retranslated, translation_model = await _sweep_drifted_translations(
            store, kit_id, schema, schema_file,
        )

    # CROSS-KIT SUPERSEDE (bd polyglot-pdf-6dz0). A new government edition is
    # usually onboarded as its own kit, so publishing it would leave TWO live
    # entries for one form -- the thing the client's form list must never show.
    # Naming the outgoing kit here unpublishes it as part of this publish.
    #
    # Ordering is deliberate: the outgoing kit is retired only AFTER every gate
    # above has passed for the incoming one. Retiring first and then failing a
    # gate would leave the form with NO live kit at all -- strictly worse than
    # the two-entry state we are fixing. The VALIDATION for replaces_kit_id
    # (malformed / self-reference / unknown / not-complete) already ran, ahead
    # of the translation sweep, above (bd polyglot-pdf-asr2a) -- this is only
    # the archive WRITE, which stays here, deferred until every gate for the
    # incoming kit has passed.
    #
    # Same-kit republish needs no flag: one kit_id is one catalogue slot, so a
    # kit always replaces itself.
    if superseded_kit is not None:
        # The lock applies to the OUTGOING kit too. The guard at the top of
        # this route only ever saw the INCOMING kit's metadata, so a
        # supersede archived and retired a second kit that no guard had
        # checked (Opus fresh-eyes round 2). Inert today -- the lock is
        # role-scoped, so a same-role holder would not be refused anyway --
        # STILL INERT after bd polyglot-pdf-5tuas, and I wrongly "corrected"
        # this comment to say otherwise -- measured: publishing is author-only,
        # and _lock_refusal returns None for every author actor, so the only
        # callers who reach here are never refused. It stays because it
        # contradicts the helper's own "every schema write" contract to omit
        # it, and because the day author-vs-author is refused, this is the
        # site that would silently write over someone's kit.
        _require_edit_lock(superseded_meta, role)

        # Archive its bytes now -- the archive is additive and harmless even if
        # the publish below fails, whereas the STATUS flip is not, so that is
        # deferred until the incoming kit is actually live (see below).
        await _archive_published_revision(store, superseded_kit, superseded_meta)

    next_meta = {**(meta or {}), "status": body.status}
    # A STATUS CHANGE HANDS THE KIT OVER, so it releases the lock. Keeping it
    # bricked the bead's headline flow: an author takes the lock to review,
    # sends the kit back to draft, and the lock stays theirs -- so the editor
    # 409s on save, on re-submit, and on BOTH lock routes, with no control
    # rendered to self-rescue (an editor is offered nothing on an author-held
    # kit, by design). The subcontractor could not do the work they were sent
    # back to do (Opus fresh-eyes round 8, reproduced end to end).
    #
    # It also outlived a publish, so a live kit advertised "Editor editing"
    # forever -- and LIVE now that bd polyglot-pdf-5tuas made locks
    # per-user, because that stale holder now actually refuses other people.
    #
    # Editing is what the lock guards, and a status transition ends the editing
    # turn either way: handed to an author for review, handed back for changes,
    # or published and write-locked. Nobody holds it across that boundary.
    kept_lock = _lock_after_transition(meta, current_status, body.status, role)
    next_meta.pop(_LOCK_KEY, None)
    if kept_lock is not None:
        next_meta[_LOCK_KEY] = kept_lock
    # Stamp the PUBLISH DATE on promotion (bd polyglot-pdf-47r3, maintainer
    # 2026-08-04). It is the revision marker for a kit with no government
    # edition date -- a firm's own intake form has no "12/2024", but it does
    # have "the version published on <date>", which is human-readable, real,
    # and meaningful in a liability record. Written only on the promotion to
    # complete: a revert to draft leaves the last publish date intact (the kit
    # WAS published then), and re-publishing after an edit moves it.
    #
    # Precisely: this stamps EVERY complete-status POST, including an idempotent
    # complete->complete re-press with no schema edit, so it records "when this
    # kit was last published", NOT "when it last changed" (Opus review on 47r3;
    # an earlier comment here overclaimed the latter). READ by
    # get_retire_candidates as the last-resort revision marker shown to an
    # author choosing which older version to retire, for a kit that declares
    # neither an edition_date nor an author_version (bd polyglot-pdf-bdedm).
    # The author-supplied version is still the field that carries edit intent.
    if body.status == "complete":
        next_meta["published_at"] = datetime.now(timezone.utc).isoformat()
        # Re-stamp readiness from the RELOADED schema this transition just
        # gated on (sprint-18 C4).
        #
        # RE-LINTED rather than reusing the gate's findings: the translation
        # drift sweep above MUTATES `schema` in place and re-persists it, and
        # the flags it writes are re-emitted as field-anchored findings by the
        # next lint. Reusing gate_findings (computed BEFORE the sweep) would
        # stamp counts describing the pre-sweep schema under a schema_sha1
        # computed from the POST-sweep one -- an internally inconsistent stamp
        # that the editor contradicts the moment anyone opens the kit (Opus
        # fresh-eyes round 2). The lint is over the same in-memory schema the
        # hash is taken from, so counts and hash now describe one object.
        #
        # Guarded for the SAME reason the save path guards its stamp: by the
        # time this runs the kit has cleared validation, the v2 stamp, the lint
        # gate and the sweep (which may already have WRITTEN re-translations),
        # so letting a stamp failure raise would 500 a publish that legitimately
        # passed every gate -- and the caller would retry a transition that
        # partly happened. An unstamped publish is a card showing the verify
        # hint; a 500 is a broken publish.
        try:
            # `verified` must match _stamp_readiness's semantics, not just
            # hardcode True (bd polyglot-pdf-ucjlu): dump_data at this point
            # came from the GATE's _load_kit_dump call above, which by design
            # collapses FormKitNotFound (no dump -- fine) and FormKitStoreError
            # (dump exists but could not be READ -- a real failure) to the
            # same None. Hardcoding verified=True stamped "fully checked" even
            # when the dump-gated rules silently never ran because the read
            # FAILED -- and since this re-stamp runs AFTER the save path
            # (bd polyglot-pdf-kwh3t) already recorded an honest verified=False
            # for that same corrupt dump, publish immediately overwrote it
            # with the dishonest claim. Re-derive whether THIS read failed --
            # not whether the dump merely doesn't exist -- via the same direct
            # read _stamp_readiness uses. The dump itself cannot have changed
            # between the gate's read and here (only `schema` was mutated by
            # the drift sweep), so re-reading it is safe and cheap.
            try:
                await store.load_json_artifact(kit_id, _ACROFORM_ARTIFACT)
                dump_verified = True
            except FormKitNotFound:
                dump_verified = True  # no dump ever existed -- not a failure
            except FormKitStoreError:
                dump_verified = False  # a real read failure
            post_sweep_findings = lint_schema(schema, dump_data)
            next_meta[_READINESS_KEY] = _readiness_stamp(
                schema, post_sweep_findings, verified=dump_verified,
            )
        except Exception:  # noqa: BLE001 -- never fail a gated publish
            _log.warning("editor_status_stamp_failed", kit_id=kit_id,
                         exc_info=True)
    try:
        await store.put_metadata(kit_id, next_meta)
    except FormKitStoreError as exc:
        _log.error("editor_status_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to update status") from exc

    # RETIRE THE OUTGOING KIT LAST -- only once the incoming one is actually
    # live (bd polyglot-pdf-6dz0). The gates above protect against a validation
    # failure, but not against this final store write failing: retiring first
    # and then failing here would leave the form with ZERO live versions, which
    # is worse than the two-entry state the supersede exists to fix. Publishing
    # first means the failure mode is TWO live entries -- visible, and fixable
    # by unpublishing the old one.
    if superseded_kit:
        try:
            # Retiring the outgoing kit is a status transition too, so it releases
            # ITS lock -- this second write merges superseded_meta verbatim and
            # kept a stale lock, recreating the same dead end one kit over
            # (round 9, reproduced). Same helper as the incoming kit so the two
            # sites cannot drift apart again -- ACTUALLY sharing it, not just
            # claiming to: the hardcoded pop this replaced agreed with the
            # helper only by accident of the current gating, so a future
            # change to the keep-rule (bd polyglot-pdf-ijntk) would have
            # applied to one site and silently not the other (round 10).
            retired_meta = {**(superseded_meta or {}), "status": "unpublished"}
            retired_kept = _lock_after_transition(
                superseded_meta, _status_of(superseded_meta), "unpublished", role)
            retired_meta.pop(_LOCK_KEY, None)
            if retired_kept is not None:
                retired_meta[_LOCK_KEY] = retired_kept
            await store.put_metadata(superseded_kit, retired_meta)
        except FormKitStoreError as exc:
            _log.error("editor_supersede_failed", kit_id=kit_id,
                       superseded=superseded_kit, error=str(exc))
            raise HTTPException(
                status_code=502,
                detail=f"{kit_id} was published, but {superseded_kit} could not "
                       "be unpublished -- BOTH are live for this form now. "
                       f"Unpublish {superseded_kit} to finish the swap.",
            ) from exc
        _log.info("editor_kit_superseded", kit_id=kit_id,
                  superseded=superseded_kit, role=role.role, actor=role.label())

    _log.info("editor_status_set", kit_id=kit_id, status=body.status, role=role.role, actor=role.label(),
              retranslated=retranslated, translation_model=translation_model)
    return KitStatusResponse(
        ok=True, status=body.status,
        retranslated=retranslated, translationModel=translation_model,
        supersededKitId=superseded_kit,
    )


# Machine-readable refusal markers for the delete guard (bd polyglot-pdf-6zhaf).
# The client must know WHICH refusal it got so it can escalate rather than dead-
# end: a refusal the human cannot get past is not a safeguard, it is a form that
# can never be cleaned up. Prefixes rather than prose, matching the pattern this
# surface already uses (AUTHOR_VERSION_REQUIRED:, NO_EDITOR_ACCESS:) -- English
# gets reworded, and here the wording decides whether an override is offered.
DELETE_NEEDS_ACK_PREFIX = "DELETE_NEEDS_ACK:"
DELETE_NEEDS_DOUBLE_ACK_PREFIX = "DELETE_NEEDS_DOUBLE_ACK:"

# The two acknowledgement LEVELS, distinct on the wire. A single boolean cannot
# express two levels: with one, `?acknowledged=true` satisfied an ever-live
# delete exactly as it satisfied a never-live one, so the "double" in
# double-confirmation lived only in the client's checkbox and any direct API
# call skipped it (fresh-eyes, bd polyglot-pdf-6zhaf). These are values the
# CALLER must name, so the server records which level was actually given
# rather than inferring it.
ACK_UNDERSTOOD = "understood"
ACK_UNDERSTOOD_PUBLISHED = "understood-published"


def _kit_was_ever_live(meta: Optional[dict]) -> bool:
    """Has this kit ever been visible to a client?

    NOT a status-string test. `unpublished` means a RETIRED FORMERLY-LIVE
    revision (bd polyglot-pdf-6dz0), so it is as live-having as `complete`;
    reading the word alone would put a retired form in the LIGHT tier, which is
    the opposite of right.

    And `published_at` alone is not enough either: measured on the demo store
    2026-08-28, kit `w7` is status=complete with NO published_at (it predates
    the stamp), so keying on the timestamp would classify a live form as
    never-published. Either signal is sufficient; neither is necessary.
    """
    if not isinstance(meta, dict):
        # Unreadable metadata is not evidence of safety. Treat as ever-live so
        # the strictest path applies -- the same fail-closed instinct as the
        # confirmation check, but escalating rather than blocking outright.
        return True
    if meta.get("status") in _PUBLISHED_STATUSES:
        return True
    return bool(meta.get("published_at"))


@router.delete("/kits/{kit_id}", response_model=KitDeleteResponse)
async def delete_editor_kit(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
    acknowledged: Optional[str] = None,
) -> KitDeleteResponse:
    """Permanently remove a kit and everything under it, archives included.

    AUTHOR ONLY, and deliberately the only destructive route in this file
    (maintainer decision 2026-08-08: "editors should not ever be able to make
    destructive actions -- their work should always be recoverable"). Editors
    are subcontractors; deletion is the accountable party's call.

    GRADUATED FRICTION, never a permanent block (maintainer decision
    2026-08-28, bd polyglot-pdf-6zhaf): "I want all the safeguards, but no form
    should ever be completely invulnerable." The previous design refused
    outright when the confirmation check was positive OR unavailable, with no
    way past -- and because un-attributable legacy records make the check
    permanently unavailable, EVERY kit became undeletable forever. A form-kit
    store then fills with junk nobody can clear. A safeguard must make a
    destructive act DELIBERATE, not IMPOSSIBLE.

    So the risk decides how much friction, not whether the door exists:

      TIER A -- never live, no records, check worked
        -> deleted. The junk-cleanup case, and it must stay easy.
      TIER B -- never live, but records exist OR the check is UNAVAILABLE
        -> 409 DELETE_NEEDS_ACK: naming what is unknown. Proceeds on ?acknowledged=true.
      TIER C -- ever live (complete/unpublished/published_at), any check result
        -> 409 DELETE_NEEDS_DOUBLE_ACK:. Proceeds only on ?acknowledged=true,
           and the client is required to double-confirm before sending it.

    Tier B is still cautious for a reason worth keeping: the confirmation sink
    is Firestore, enabled by the deploy env; with it off the check falls back to
    a local JSONL that dies with the instance, so an operator running locally
    against the real bucket sees an empty file and would otherwise conclude "no
    records". Unverified is not the same as safe -- it just is not a dead end.

    WHAT IS ACTUALLY DESTROYED, stated precisely because the warning copy
    depends on it: delete_kit removes only this kit's own prefix -- schema, PDF,
    metadata, revision archives. The confirmation records live in a SEPARATE
    Firestore collection and survive. So a delete does not erase anyone's
    agreement; it erases THE REVISION THAT AGREEMENT NAMES, leaving a record
    that points at a document nobody can produce any more. Telling an author
    "this deletes their agreement records" would be false, and false warnings
    teach people to click through true ones.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    # 404 before anything else, so deleting a typo'd id says so plainly rather
    # than reporting a guard result about a kit that was never there. The meta
    # is KEPT now (it was discarded before): the tier depends on whether this
    # kit was ever live, and its label is what the refusal must name.
    meta, _files = await _load_meta_or_404(store, kit_id)

    ever_live = _kit_was_ever_live(meta)

    # The check still runs, and its OUTCOME still matters -- it just no longer
    # decides whether deletion is possible, only how loudly we ask.
    unverifiable: Optional[str] = None
    try:
        has_records = kit_has_confirmation_records(kit_id)
    except ConfirmationCheckUnavailable as exc:
        has_records = False
        unverifiable = str(exc)

    # The human sees the LABEL; the id is internal (and the editor currently
    # shows ids where labels belong -- bd polyglot-pdf-kztlr), so a refusal that
    # names only the id is unreadable against the catalogue on screen.
    label = (meta or {}).get("label") or kit_id

    # An ever-live kit needs the STRONGER token specifically -- the weaker one
    # does not escalate into it, or the tier is decorative.
    if ever_live and acknowledged != ACK_UNDERSTOOD_PUBLISHED:
        _log.info("editor_kit_delete_needs_double_ack", kit_id=kit_id,
                  role=role.role, actor=role.label(), has_records=has_records,
                  unverifiable=unverifiable)
        raise HTTPException(
            status_code=409,
            detail=(
                DELETE_NEEDS_DOUBLE_ACK_PREFIX
                + f' "{label}" has been published, so clients may have filled it '
                f"and agreed to what they saw. Their agreement records will "
                f"survive this deletion -- but the exact form revision those "
                f"records name will be gone, so you would no longer be able to "
                f"show what they agreed to. This cannot be undone. Unpublishing "
                f"instead hides it from clients and keeps every file."
            ),
        )

    if (has_records or unverifiable) and acknowledged not in (
            ACK_UNDERSTOOD, ACK_UNDERSTOOD_PUBLISHED):
        # Never live, but we either found records or could not look. Say which,
        # because the remedy differs and the old message conflated them.
        reason = (
            "it has confirmation records, so someone has already filled it"
            if has_records else
            "the confirmation record store cannot be consulted right now, so "
            "whether ANY form has been filled is unknown -- this is not "
            "specific to this one"
        )
        _log.info("editor_kit_delete_needs_ack", kit_id=kit_id, role=role.role,
                  actor=role.label(), has_records=has_records,
                  unverifiable=unverifiable)
        raise HTTPException(
            status_code=409,
            detail=(
                DELETE_NEEDS_ACK_PREFIX
                + f' "{label}" was never published, but {reason}. Deleting it '
                f"removes the form, its PDF and every archived version, "
                f"permanently."
            ),
        )

    try:
        removed = await store.delete_kit(kit_id)
    except FormKitNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Kit not found: {kit_id}") from exc
    except FormKitStoreError as exc:
        raise HTTPException(
            status_code=502, detail=f"Unable to delete the kit: {exc}"
        ) from exc

    # ATTRIBUTION IS THE PRICE OF THE OVERRIDE. A delete that got past a warning
    # must name who waved it through and what they were warned about, or the
    # graduated path is just a slower way to lose the record silently.
    _log.info("editor_kit_deleted", kit_id=kit_id, role=role.role,
              actor=role.label(), objects_removed=removed,
              acknowledged=acknowledged, ever_live=ever_live,
              had_records=has_records, unverifiable=unverifiable)
    return KitDeleteResponse(ok=True, kitId=kit_id, objectsRemoved=removed)


@router.post("/kits/{kit_id}/lock", response_model=KitLockResponse)
async def take_editor_kit_lock(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> KitLockResponse:
    """Take this kit for editing, or report who already has it.

    An AUTHOR can always take a lock back from an editor (maintainer decision
    2026-08-11) -- that preemption doubles as the stale-lock release, so there
    is no timer. A clock that steals a lock from someone actively working is
    worse than a human choosing to take it.

    Same-role contention is REFUSED (bd polyglot-pdf-5tuas): the lock names a
    PERSON, so a second editor taking a kit the first holds is a real
    collision, and the refusal names the holder. Re-taking your OWN lock is
    not a steal. An AUTHOR still preempts anyone, including another author --
    that IS the stale-lock release, and there is no timer.

    A lock written BEFORE 5tuas carries no uid; it is unattributable, so
    same-role contention falls back to the old ALLOW for it rather than
    stranding an editor on a kit nobody can be shown to hold.
    """
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    _refuse_if_metadata_unreadable(meta, files, kit_id, "taking the lock")

    holder = _lock_holder(meta)
    holder_uid = _lock_holder_uid(meta)
    refusal = _lock_refusal(holder, role, holder_uid,
                            _lock_holder_label(meta)) if holder else None
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)

    # PREEMPTION is taking it from a different PERSON now, not a different
    # role. Re-taking your own lock (a refresh, a second tab) is not a
    # preemption and must not log as one.
    preempted = holder is not None and (
        holder_uid != role.uid if holder_uid else holder != role.role)
    # The lock names a PERSON (bd polyglot-pdf-5tuas). Plain JSON strings only:
    # writing the actor OBJECT here would put a non-serializable value straight
    # into metadata.json -- that broke every lock take in an earlier round.
    # "label" is the holder's EMAIL. TWO publish surfaces, and they differ --
    # a reviewer and I each had one half right, so both are named here:
    #   * the GCS BUCKET (deploy-all.sh + scripts/deploy-form-kit.sh,
    #     collect_publishable_kit_files) takes everything not "_"-prefixed, so
    #     metadata.json DOES go there;
    #   * the FRONTEND BUNDLE (frontend/scripts/kitAssetFilter.ts,
    #     publishableKitFiles) is a strict two-file allowlist (schema + pdf),
    #     so metadata.json NEVER reaches the public Hosting bundle -- that
    #     module's docstring says it was excluded precisely because it carries
    #     editing_lock.
    # Checked and decided rather than assumed:
    #   * the bucket is NOT public -- uniform access, no allUsers, served
    #     through the authenticated backend;
    #   * docs/standards/hipaa-pii-policy.md governs APPLICANT data (A-numbers,
    #     names, addresses, DOBs), not staff identity;
    #   * naming the holder to a human IS the audit trail this epic exists to
    #     create -- "an editor holds this" was the problem.
    # Maintainer chose to store it (2026-08-27) over resolving uid -> email at
    # display time, which would need the Firebase user-record permission the
    # deployed service account deliberately lacks.
    next_meta = {**(meta or {}), _LOCK_KEY: {
        "role": role.role,
        "uid": role.uid,
        # NOT "label": deploy-all.sh and scripts/deploy-form-kit.sh grep
        # metadata.json for '"label"' with head -1 and put the result in the
        # published manifest as the form's DISPLAY NAME. A kit with no
        # top-level label (none exist today, but nothing prevents one) would
        # publish this contractor's EMAIL as the form's name in the picker --
        # reproduced. Renaming the key is the fix that does not depend on JSON
        # key ORDER, which is what currently saves it. bd polyglot-pdf-0ygyv
        # still covers hardening the deploy-side grep.
        "holder_label": role.label(),
    }}
    try:
        await store.put_metadata(kit_id, next_meta)
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to take the lock") from exc

    if preempted:
        # took_from_label, not just the role: author-over-author preemption is
        # newly reachable (bd polyglot-pdf-5tuas), so took_from="author" alone
        # now means "some author, we will not say which" -- on the one log line
        # that records a lock being TAKEN FROM a person, which is the audit
        # artifact this epic exists to produce.
        _log.info("editor_kit_lock_preempted", kit_id=kit_id, role=role.role,
                  actor=role.label(), took_from=holder,
                  took_from_label=_lock_holder_label(meta))
    return KitLockResponse(ok=True, kitId=kit_id, heldBy=role.role,
                           heldByLabel=role.label(), preempted=preempted)


@router.delete("/kits/{kit_id}/lock", response_model=KitLockResponse)
async def release_editor_kit_lock(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> KitLockResponse:
    """Release this kit. An author may release anyone's lock; an editor may
    release only a lock THEY hold (bd polyglot-pdf-5tuas) -- they can neither
    evict an author nor release another editor's kit. A legacy lock carrying
    no uid falls back to the old role test, so nobody is stranded on one."""
    kit_id = _safe_kit_id(kit_id)
    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    _refuse_if_metadata_unreadable(meta, files, kit_id, "releasing the lock")

    holder = _lock_holder(meta)
    if holder is None:
        return KitLockResponse(ok=True, kitId=kit_id, heldBy=None)
    refusal = _lock_refusal(holder, role, _lock_holder_uid(meta),
                            _lock_holder_label(meta))
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)

    next_meta = {k: v for k, v in (meta or {}).items() if k != _LOCK_KEY}
    try:
        await store.put_metadata(kit_id, next_meta)
    except FormKitStoreError as exc:
        raise HTTPException(status_code=502, detail="Unable to release the lock") from exc
    # Releasing a lock is a MUTATION of metadata.json and was the one such route
    # that recorded nothing at all -- so "who released the lock on this kit"
    # was unanswerable, which is the audit question this bead exists to answer.
    _log.info("editor_kit_lock_released", kit_id=kit_id, role=role.role,
              actor=role.label(), held_by=holder)
    return KitLockResponse(ok=True, kitId=kit_id, heldBy=None)


@router.post("/kits/{kit_id}/label")
async def set_editor_kit_label(
    kit_id: str,
    body: KitLabelBody,
    role: Annotated[EditorActor, Depends(require_editor_role)],
) -> dict:
    """Rename a kit's DISPLAY label (bd polyglot-pdf-15ic), preserving every
    other metadata key -- the exact read-merge-write shape of the status flip.

    The label is pure display: the catalogue and the voice app's form picker
    render it, but nothing keys on it (the kit's identity is the immutable
    kit_id / storage path). Onboarding derives a label from the PDF filename, so
    nameless uploads collide into "Form", "Form 2", ... -- this lets a human fix
    that after the fact. The identity is deliberately NOT renameable here.
    """
    kit_id = _safe_kit_id(kit_id)
    label = _safe_label(body.label)
    store = get_form_kit_store()
    meta, _files = await _load_meta_or_404(store, kit_id)
    next_meta = {**(meta or {}), "label": label}
    try:
        await store.put_metadata(kit_id, next_meta)
    except FormKitStoreError as exc:
        _log.error("editor_label_save_failed", kit_id=kit_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Unable to update label") from exc
    _log.info("editor_label_set", kit_id=kit_id, role=role.role, actor=role.label())
    return {"ok": True, "label": label}


# --- author tier: PDF onboarding + hosted extraction (bd polyglot-pdf-92qe.3) --
#
# The (a)-tier contractor permission from the 2026-07-01 goal: collect (upload a
# blank AcroForm PDF into the shared store), extract (run the PDF->schema
# authoring pass server-side), review. Both routes require the AUTHOR role --
# extraction spends paid model tokens and onboarding creates kits, neither of
# which the polish-only editor tier may do.

# Mirror of the editor's deriveFormId (formKitDirectory.ts): a URL-safe kit id
# from an uploaded filename ("Form I-90 (1).pdf" -> "form-i-90-1"). CAPPED well
# under _KIT_ID_RE's 128-char limit: a realistic long download name ("USCIS
# Form I-90 Application to Replace ... Downloaded From ....pdf") would
# otherwise derive a >128-char slug and 400 with a baffling "Invalid kit id"
# (fresh-eyes, reproduced live). 64 chars leaves ample room for the -2/-3
# uniquifier suffixes.
_KIT_ID_MAX_DERIVED = 64


def _derive_kit_id(filename: str) -> str:
    base = re.sub(r"\.pdf$", "", filename or "", flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    slug = slug[:_KIT_ID_MAX_DERIVED].rstrip("-")
    return slug or "form"


def _friendly_label(kit_id: str) -> str:
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), kit_id.replace("-", " ").replace("_", " "))


def _safe_label(raw: str) -> str:
    """Validate a caller-supplied DISPLAY label (bd 15ic); returns it stripped.

    Raises 422 on: blank; >200 chars (a display name, not a document); a double
    quote, backslash, or control character. The character ban is LOAD-BEARING,
    not cosmetic: the deploy scripts extract the label from metadata.json with
    a grep/sed pipeline and splice it into index.json by string concatenation
    (deploy-all.sh / scripts/deploy-form-kit.sh) -- a quote or backslash there
    truncates the extraction and ships INVALID manifest JSON, which the voice
    app cannot parse (no forms would load). Opus review, bd 15ic.
    """
    label = (raw or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="Label must not be empty")
    if len(label) > 200:
        raise HTTPException(status_code=422, detail="Label too long (max 200 characters)")
    if '"' in label or "\\" in label or any(ord(ch) < 32 for ch in label):
        raise HTTPException(
            status_code=422,
            detail="Label may not contain double quotes, backslashes, or "
                   "control characters",
        )
    return label


# ONE extraction subprocess per instance at a time: each run holds a PDF +
# schema in memory and spawns a Python child; serializing keeps the container's
# memory bounded and makes concurrent-write races on one kit impossible. A
# second author's request queues (the HTTP request waits; Cloud Run's
# --timeout=3600 covers it).
_extract_semaphore = asyncio.Semaphore(1)

# Serialize the onboard list->derive->write window (fresh-eyes, reproduced):
# two concurrent uploads deriving the SAME kit id both read the listing
# snapshot, both uniquify to the same id, and one author's PDF silently
# vanishes behind a false 200. Per-instance serialization closes the reachable
# race (one Cloud Run instance handles a small contractor pool's uploads);
# a cross-instance collision remains theoretically possible and is accepted --
# same-second same-filename uploads from two authors on two instances.
#
# The lock is PER EVENT LOOP (lazy, keyed weakly by the running loop). An
# asyncio.Lock binds to a loop only on a CONTENDED acquire (the uncontended
# fast path never touches the loop check), so a module-level Lock would work
# for most sequential tests -- but any genuinely contended acquire on a second
# loop (the TestClient runs each request on its own) raises RuntimeError. The
# per-loop map removes that trap defensively; under uvicorn (one loop for the
# process) exactly one entry ever exists.
_onboard_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _get_onboard_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _onboard_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _onboard_locks[loop] = lock
    return lock


# Serialize the guidance-regeneration load -> enrich -> apply -> put_schema
# window (bd polyglot-pdf-gnb0). Same shape and same two reasons as the
# extract semaphore above: an LLM call plus a stored-schema rewrite.
#   - LOST UPDATE: the route reads the schema, mutates it in memory across a
#     minutes-long model call, and writes it back with no version check, so two
#     overlapping regenerates silently discarded one side's write. SCOPE: this
#     lock closes regenerate-vs-regenerate ONLY. A regenerate racing a
#     PUT /schema (or any other put_schema caller -- 7 write sites, this is the
#     one inside a lock) is still unguarded, because put_schema has no version
#     check; that broader race is bd polyglot-pdf-gpghk. Do not read this lock
#     as making the schema-write path safe against the editor's own save.
#   - The CLI transport's scratch file used to be keyed on the PID, so two
#     concurrent calls in this ONE process fought over one path. That is fixed
#     at the source (llm_providers._cli_scratch_path is per-call now), and this
#     lock is the independent second guard: the store write needs serializing
#     whichever provider ran.
# Per event loop for the same reason the onboard lock is -- see its comment.
_guidance_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _get_guidance_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _guidance_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _guidance_locks[loop] = lock
    return lock


def _repo_root() -> Path:
    """The checkout/container root: backend/routes/x.py -> two parents up.

    Locally this is the repo root; in the Cloud Run image it is /app (the image
    copies backend/ AND scripts/ under /app -- see backend/Dockerfile).
    """
    return Path(__file__).resolve().parents[2]


async def _read_upload_pdf(pdf: UploadFile, max_mb: float) -> bytes:
    """Read + sanity-check an uploaded PDF (size cap, %PDF magic).

    STREAMED in chunks with the cap enforced as bytes arrive (fresh-eyes): a
    single `await pdf.read()` would materialize an oversized body fully in
    memory before rejecting it. Cloud Run's ~32 MB request ceiling bounds the
    worst case, but check-as-you-read is the right shape regardless.
    """
    limit = int(max_mb * 1024 * 1024)
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await pdf.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"PDF is larger than the {max_mb:g} MB upload limit",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    # Magic-byte check: the `accept` filter client-side is advisory; a renamed
    # HTML page must not land in the store as form.pdf.
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="The file is not a PDF")
    return data


@router.post("/kits", response_model=EditorKitInfo)
async def onboard_editor_kit(
    role: Annotated[EditorActor, Depends(require_author_role)],
    pdf: Annotated[UploadFile, File(description="The blank AcroForm PDF")],
    label: Annotated[Optional[str], Form()] = None,
) -> EditorKitInfo:
    """Create a new kit in the shared store from an uploaded form PDF.

    The hosted counterpart of the local catalogue's drag-drop onboarding
    (formKitDirectory.onboardPdf): derive a URL-safe kit id from the filename
    (uniquified with -2/-3... if taken), write form.pdf + metadata.json
    (status draft). No schema yet -- extraction is the separate step.
    """
    settings = get_settings()
    data = await _read_upload_pdf(pdf, settings.EXTRACTOR_MAX_PDF_MB)

    store = get_form_kit_store()
    # The list->derive->write window runs under the onboard lock: without it,
    # two concurrent uploads deriving the same id both pass the uniquifier and
    # one PDF silently loses (fresh-eyes, reproduced live).
    async with _get_onboard_lock():
        try:
            existing = await store.list_kit_files()
        except FormKitStoreError as exc:
            raise HTTPException(status_code=502, detail="Unable to list kits") from exc

        base = _derive_kit_id(pdf.filename or "form")
        kit_id = base
        n = 2
        while kit_id in existing:
            kit_id = f"{base}-{n}"
            n += 1
        # The derived id must survive the same guard every later route applies.
        kit_id = _safe_kit_id(kit_id)

        # A caller-supplied label goes through the same validation as a rename
        # (the deploy-manifest pipeline cannot tolerate quotes/backslashes --
        # see _safe_label); absent/blank falls back to the derived name.
        kit_label = (_safe_label(label) if isinstance(label, str) and label.strip()
                     else _friendly_label(kit_id))
        try:
            await store.put_pdf_bytes(kit_id, data, "form.pdf")
            await store.put_metadata(kit_id, {"label": kit_label, "status": "draft"})
        except FormKitStoreError as exc:
            _log.error("editor_onboard_failed", kit_id=kit_id, error=str(exc))
            raise HTTPException(status_code=502, detail="Unable to store the PDF") from exc

    _log.info("editor_kit_onboarded", kit_id=kit_id, size_bytes=len(data), role=role.role, actor=role.label())
    return EditorKitInfo(
        id=kit_id, label=kit_label, description=None, status="draft",
        hasSchema=False, hasPdf=True, schemaFile="schema.json", pdfFile="form.pdf",
    )


class ExtractResponse(BaseModel):
    ok: bool
    detail: str
    schemaFile: Optional[str] = None
    fieldCount: Optional[int] = None
    # Store-with-issues (bd polyglot-pdf-v96b, P5.3a): a parseable draft with >= 1
    # field is STORED even when it is lint-dirty or invalid, and the response
    # carries the lint counts so the editor surfaces them. storedWithIssues is
    # True exactly when the stored draft has lint ERRORs or failed validation
    # (extractor tri-state exit 3); the draft is un-promotable until repaired
    # (the two-gate seam -- promotion still 409s on lint ERRORs).
    errorCount: int = 0
    warningCount: int = 0
    storedWithIssues: bool = False


@router.post("/kits/{kit_id}/extract", response_model=ExtractResponse)
async def extract_editor_kit(
    kit_id: str,
    role: Annotated[EditorActor, Depends(require_author_role)],
    force: Annotated[bool, Form()] = False,
    translate_options: Annotated[bool, Form(
        description="Also bake option label_translations (bd 2h9j; pro-tier, "
                    "one call per language). Uncheck for cheap "
                    "extraction-strategy test runs."
    )] = True,
    enrich_guidance: Annotated[bool, Form(
        description="Also author booklet-grounded field guidance "
                    "(bd wsao.6; authoring + judge LLM calls). Uncheck for "
                    "cheap extraction-strategy test runs."
    )] = True,
    instructions_pdf: Annotated[Optional[UploadFile], File(
        description="OPTIONAL official instructions PDF; enriches help text"
    )] = None,
) -> ExtractResponse:
    """Run the PDF -> draft-schema authoring pass for a kit, server-side.

    The hosted counterpart of the Vite dev server's /api/extract (which spawns
    the extractor on the maintainer's machine): stream the kit's PDF from the
    store to a temp dir, run scripts/authoring/extract_form.py as a subprocess
    (model = EXTRACTOR_MODEL, a gemini-* model -- the local `claude` CLI does
    not exist in the container).

    STORE-WITH-ISSUES (bd polyglot-pdf-v96b, P5.3a): a parseable draft with >= 1
    field is stored EVEN when it is lint-dirty or fails validation -- the response
    returns 200 carrying the lint counts and a storedWithIssues flag so the editor
    surfaces them and the author repairs in place. Only a hard failure (no usable
    draft: crash, timeout, no JSON, zero fields) is a 5xx. The AcroForm dump is
    persisted as the kit's acroform.json artifact alongside the draft. The draft
    stays UN-PROMOTABLE until repaired -- the two-gate seam: mark-complete still
    409s on lint ERRORs (store != promote).

    Synchronous by design: Cloud Run's --timeout=3600 covers a minutes-long run,
    and the editor shows elapsed progress. Refuses to clobber an existing schema
    unless force=true (the same no-overwrite contract as the dev endpoint).
    """
    kit_id = _safe_kit_id(kit_id)
    settings = get_settings()
    if not (settings.EXTRACTOR_MODEL or "").lower().startswith("gemini"):
        raise HTTPException(
            status_code=503,
            detail="Hosted extraction needs a gemini-* EXTRACTOR_MODEL "
                   "(the local claude CLI is not available on the server)",
        )
    # Extraction is "configured" if it can authenticate to Gemini AT ALL: either
    # Vertex AI (ADC / service account -- how Cloud Run runs, no key) OR an AI
    # Studio key (local dev). The provider picks the same way (llm_providers.py),
    # so this gate must not demand a key when VERTEXAI is on, or it would 503
    # before ever reaching the working Vertex path (bd polyglot-pdf-fyq4).
    if not (settings.VERTEXAI or settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")):
        raise HTTPException(
            status_code=503,
            detail="Hosted extraction is not configured (set VERTEXAI=true for "
                   "service-account auth, or provide a GEMINI_API_KEY)",
        )

    store = get_form_kit_store()
    meta, files = await _load_meta_or_404(store, kit_id)
    schema_file, pdf_file = _resolve_meta_names(meta)
    # A PUBLISHED kit's schema is what the voice app streams AND what its
    # confirmation records were confirmed against. force=true would overwrite it
    # in place -- going live unvalidated (the same hazard the lenient-save gate
    # closes) and destroying the superseded revision without passing through the
    # revert-to-draft archive hook, so an old record could name a schema the
    # store can no longer produce (bd polyglot-pdf-w3zw; this route was the one
    # write path missing the gate). Require the explicit revert first, exactly
    # like save/repair/translate/derive/regenerate.
    if _is_write_locked(meta):
        raise HTTPException(
            status_code=409,
            detail=f"{_lock_reason(meta)} (Re-extraction overwrites the schema "
                   "in place, losing the revision its confirmation records "
                   "name.)",
        )
    _require_edit_lock(meta, role)
    if pdf_file not in files:
        raise HTTPException(status_code=409, detail=f"Kit {kit_id} has no {pdf_file} to extract from")
    if schema_file in files and not force:
        raise HTTPException(
            status_code=409,
            detail=f'"{schema_file}" already exists for kit "{kit_id}"; re-extracting '
                   "would overwrite it (pass force=true to replace it)",
        )

    script = _repo_root() / "scripts" / "authoring" / "extract_form.py"
    if not script.exists():
        raise HTTPException(
            status_code=503,
            detail="The extraction script is not present on this server "
                   "(the image must include scripts/authoring + scripts/bakeoff)",
        )

    try:
        pdf_bytes = await store.load_pdf_bytes(kit_id, pdf_file)
    except (FormKitNotFound, FormKitStoreError) as exc:
        raise HTTPException(status_code=502, detail="Unable to read the kit PDF") from exc

    instructions_bytes: Optional[bytes] = None
    if instructions_pdf is not None and (instructions_pdf.filename or "") != "":
        instructions_bytes = await _read_upload_pdf(
            instructions_pdf, settings.EXTRACTOR_MAX_PDF_MB
        )

    async with _extract_semaphore:
        tmp_dir = tempfile.mkdtemp(prefix=f"extract_{kit_id}_")
        try:
            tmp = Path(tmp_dir)
            pdf_path = tmp / "form.pdf"
            out_path = tmp / "schema.json"
            # extract_form writes the AcroForm dump next to --out as
            # <out-stem>_acroform.json under --keep-dump; we persist it as the
            # kit's acroform.json artifact (bd v96b) so the promotion gate's
            # dump-widget-claim rule and the P5.3c widget picker can use it.
            dump_out_path = out_path.with_name(out_path.stem + "_acroform.json")
            pdf_path.write_bytes(pdf_bytes)
            cmd = [
                sys.executable, str(script),
                "--pdf", str(pdf_path),
                "--out", str(out_path),
                "--model", settings.EXTRACTOR_MODEL,
                "--keep-dump",
            ]
            if translate_options:
                # Pass the settings-resolved model explicitly: the child env
                # may not carry OPTION_TRANSLATION_MODEL (same reasoning as
                # the VERTEXAI pin below).
                cmd += ["--translation-model", settings.OPTION_TRANSLATION_MODEL]
            else:
                cmd += ["--no-translate-options"]
            # Same reasoning for the guidance stage (bd wsao.6): without this
            # the stage's model falls through to the raw INSTRUCTIONS_MODEL /
            # EXTRACTOR_MODEL env vars and then the local claude CLI -- absent
            # in this container -- so it would silently degrade to the naive
            # fallback on a correctly-configured host. The opt-out mirrors
            # translate_options: the guidance stage is the LARGER of the two
            # LLM add-ons, so a cheap test run must be able to skip it too.
            if enrich_guidance:
                cmd += ["--guidance-model", settings.EXTRACTOR_MODEL]
            else:
                cmd += ["--no-enrich-guidance"]
            if instructions_bytes is not None:
                instructions_path = tmp / "instructions.pdf"
                instructions_path.write_bytes(instructions_bytes)
                cmd += ["--instructions-pdf", str(instructions_path)]

            # Pass the RESOLVED auth mode to the subprocess so the extractor's
            # provider (llm_providers.py) picks the same client the gate above
            # authorized. settings.VERTEXAI is the source of truth (config.py
            # defaults it True when unset); without pinning it here, the child
            # would re-read a possibly-unset VERTEXAI env with the opposite
            # default and could take the key path the gate did not require
            # (bd polyglot-pdf-fyq4).
            child_env = {
                **os.environ,
                "PYTHONUTF8": "1",
                "VERTEXAI": "true" if settings.VERTEXAI else "false",
            }

            def _run() -> subprocess.CompletedProcess:
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=settings.EXTRACTOR_TIMEOUT_SEC,
                    cwd=str(_repo_root()),
                    env=child_env,
                )

            _log.info("editor_extract_start", kit_id=kit_id,
                      model=settings.EXTRACTOR_MODEL,
                      translate_options=translate_options,
                      with_instructions=instructions_bytes is not None)
            try:
                proc = await anyio.to_thread.run_sync(_run)
            except subprocess.TimeoutExpired as exc:
                _log.error("editor_extract_timeout", kit_id=kit_id,
                           timeout_s=settings.EXTRACTOR_TIMEOUT_SEC)
                raise HTTPException(
                    status_code=504,
                    detail=f"Extraction timed out after "
                           f"{settings.EXTRACTOR_TIMEOUT_SEC:g}s",
                ) from exc

            lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
            last_line = lines[-1] if lines else "(no output)"
            # Scrub the internal temp paths from the pipeline's detail line on
            # EVERY path -- an INVALID/store-with-issues draft (a common, expected
            # outcome) names the temp --out path in its message, and the detail
            # must not leak internals the clean path scrubs (Opus fallback review,
            # PR #282). Same discipline as the dev endpoint.
            last_line = (last_line
                         .replace(str(out_path), schema_file)
                         .replace(str(tmp), "")
                         .replace(tmp_dir, ""))

            # Store-with-issues (bd v96b): the extractor's tri-state exit code
            # distinguishes a usable-but-imperfect draft (EXIT_ISSUES=3 -> STORE
            # it with its report) from no usable draft (EXIT_HARD_FAIL=1 -> 502).
            # A crash exits with neither 0 nor 3. We ALSO re-derive the floor from
            # the written draft (parseable + >=1 field) rather than trusting the
            # exit code alone, so a mis-exit can never store garbage.
            if not out_path.exists():
                _log.error("editor_extract_failed", kit_id=kit_id,
                           exit_code=proc.returncode, detail=last_line[:400])
                raise HTTPException(
                    status_code=502,
                    detail=f"Extraction failed (exit {proc.returncode}): {last_line[:400]}",
                )

            try:
                schema = json.loads(out_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Extractor wrote an unreadable schema: {exc}",
                ) from exc
            # The store-with-issues FLOOR: a dict carrying at least one FIELD-
            # SHAPED (dict) member in `fields`. Checking only "non-empty list" is
            # not enough (fresh-eyes): a crash mid-write can leave a non-empty
            # list of NON-DICT junk (["a","b"]) that lint_schema silently filters
            # out (so it reports 0 findings) -- storing it would report a false
            # "clean success" with a junk field count. The floor is re-derived
            # from the WRITTEN content (dict members), not the exit code, so a
            # mis-exit can never store garbage. real_fields is reused below for
            # an honest field count.
            real_fields = (
                [f for f in schema["fields"] if isinstance(f, dict)]
                if isinstance(schema, dict) and isinstance(schema.get("fields"), list)
                else []
            )
            if not real_fields:
                _log.error("editor_extract_no_usable_draft", kit_id=kit_id,
                           exit_code=proc.returncode, detail=last_line[:400])
                raise HTTPException(
                    status_code=502,
                    detail="Extractor produced no usable draft (a schema with at "
                           "least one field is required)",
                )

            # Read the extractor's persisted dump. A missing/unreadable dump is
            # the legitimate dump-less path (the store-time lint below and the
            # promotion gate both then run dump-less, so they AGREE); it is only
            # a STORED dump that must stay consistent with the stored schema.
            dump_data: Optional[dict] = None
            if dump_out_path.exists():
                try:
                    dump_data = json.loads(dump_out_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    dump_data = None

            # Persist the dump artifact BEFORE the schema, and make it FATAL: the
            # dump is the gating input for the dump-widget-multiclaim ERROR at the
            # promotion gate, so a schema stored WITHOUT its dump would let a
            # dump-only error the author saw at store time silently vanish at
            # promotion -- re-opening the two-gate seam (Opus fallback review, PR
            # #323). Dump-first ordering means a dump-write failure 502s before
            # anything is stored (no inconsistent state); a later schema-write
            # failure leaves only an orphan dump, overwritten on the next extract.
            if isinstance(dump_data, dict):
                try:
                    await store.put_json_artifact(
                        kit_id, dump_data, _ACROFORM_ARTIFACT
                    )
                except FormKitStoreError as exc:
                    _log.error("editor_extract_dump_store_failed",
                               kit_id=kit_id, error=str(exc))
                    raise HTTPException(
                        status_code=502,
                        detail="Extraction succeeded but its PDF-widget map could "
                               "not be stored (needed to validate the draft)",
                    ) from exc
            try:
                await store.put_schema(kit_id, schema, schema_file)
            except FormKitStoreError as exc:
                raise HTTPException(
                    status_code=502, detail="Extraction succeeded but the schema "
                                            "could not be stored",
                ) from exc

            # Lint the stored draft (dump-aware when we have it) so the response
            # carries the counts the editor surfaces -- the SAME schema_lint the
            # promotion gate uses, so store-with-issues and promote agree.
            findings = lint_schema(schema, dump_data)
            error_count = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
            warning_count = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
            stored_with_issues = (
                proc.returncode == _EXTRACT_EXIT_ISSUES or error_count > 0
            )

            # Count REAL (dict-shaped) fields, not the raw list length -- a list
            # with non-dict junk must not overstate the usable field count in the
            # response/log (fresh-eyes; same root cause as the floor above).
            field_count = len(real_fields)
            _log.info("editor_extract_done", kit_id=kit_id, fields=field_count,
                      role=role.role, actor=role.label(), errors=error_count, warnings=warning_count,
                      stored_with_issues=stored_with_issues)
            return ExtractResponse(
                ok=True, detail=last_line, schemaFile=schema_file,
                fieldCount=field_count, errorCount=error_count,
                warningCount=warning_count, storedWithIssues=stored_with_issues,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
