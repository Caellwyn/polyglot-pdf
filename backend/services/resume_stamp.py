"""The resume stamp: identity carried inside the client's own saved PDF.

bd polyglot-pdf-dft1. Maintainer, 2026-08-27: *"We already have a 'save'
function that saves the form as a pdf. I bet we can piggy back off of that to
let/encourage users to save their form locally, and then provide a way to
resume sessions later. We can track the link ids used, and the form session id
in pdf metadata to allow the resume."*

WHAT PROBLEM THIS SOLVES. Today a client who steps away for an hour loses
everything: the browser drops its form state after 60 minutes and re-initialises
with no field values. A client filling their form on a Saturday who runs out of
voice budget -- or simply closes the tab -- cannot reach the firm until Monday
and has nothing to come back to.

The saved PDF fixes it with NO server storage, which keeps the stateless-
architecture rule intact. Verified with PyMuPDF before this was written: custom
JSON in PDF metadata round-trips byte-identical, AND filled field values read
back out of a saved document. So the file the client already has is a complete
save file -- their answers in the form fields, their identity here.

=======================================================================
THIS IS NOT A CREDENTIAL. It is a HINT, and the distinction is the whole
security story.
=======================================================================

A client can edit a PDF's metadata with free tools. Nothing in this payload may
therefore grant access, entitlement, or spend. On resume:

  * ENTITLEMENT still comes from the signed link (bd ugm6). A stamped
    form_session_id does not authenticate anybody.
  * The kit_id here is a SUGGESTION about which form to reopen. It must be
    validated against what the caller is actually allowed to see -- never
    trusted to widen access.
  * The jti list is for AGGREGATION ONLY (bd polyglot-pdf-1uyof: one client's
    form should read as one record even when it took two links). A forged jti
    buys nothing: spend is keyed on the SIGNED token's jti at the socket, not
    on anything a PDF says.

Read the payload as untrusted input from the internet, because that is exactly
what it is.

WHY NO CLIENT IDENTIFIER. Same invariant as the link token and the redemption
record: we hold a pseudonym, the firm holds identity. A saved PDF is a file the
client may email, print, or hand to someone -- putting a client identifier in
its metadata would leak identity into an artifact we do not control. The
form_session_id is OUR pseudonym and is already in our own telemetry.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import structlog

_log = structlog.get_logger(__name__)

# Bumped when the payload's SHAPE changes incompatibly. A reader that does not
# recognise a version must decline to resume rather than guess -- a
# half-understood resume silently drops a client's answers.
STAMP_VERSION = 1

# The PDF metadata key the payload rides in. `keywords` is a standard Info-dict
# field every PDF tool preserves; a custom key risks being dropped by whatever
# the client's viewer does on save.
STAMP_KEY = "keywords"

# A stamp is small by design. This bound is a parse-side guard against a
# hand-edited file carrying megabytes of junk into json.loads.
MAX_STAMP_BYTES = 8192


def build_stamp(
    form_session_id: Optional[str],
    kit_id: Optional[str],
    link_jtis: Optional[list[str]] = None,
    schema_version: Optional[str] = None,
) -> Optional[str]:
    """Build the JSON payload to stamp into a filled PDF.

    Returns None when there is nothing worth stamping (no form_session_id),
    which is the STAFF case -- a staff member downloading a form does not need
    a resume hint, and stamping one would put session ids into documents that
    leave the firm.
    """
    if not isinstance(form_session_id, str) or not form_session_id:
        return None

    payload: dict[str, Any] = {
        "v": STAMP_VERSION,
        "fsid": form_session_id,
    }
    if isinstance(kit_id, str) and kit_id:
        payload["kit"] = kit_id
    if isinstance(schema_version, str) and schema_version:
        payload["sv"] = schema_version
    if link_jtis:
        # Ordered, deduplicated, strings only. The ORDER is the client's
        # link history (bd polyglot-pdf-1uyof), so preserve it rather than
        # sorting -- "which link came first" is the useful fact.
        seen: set[str] = set()
        clean: list[str] = []
        for j in link_jtis:
            if isinstance(j, str) and j and j not in seen:
                seen.add(j)
                clean.append(j)
        if clean:
            payload["jtis"] = clean

    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def parse_stamp(raw: Optional[str]) -> Optional[dict[str, Any]]:
    """Read a stamp back. Returns None for anything unusable.

    NEVER RAISES. This parses a file a client can hand-edit, so every failure
    mode -- absent, truncated, not JSON, wrong type, unknown version, oversized
    -- degrades to "no resume hint" rather than an exception. A client whose
    PDF confuses us must be told their form cannot be resumed, not shown a
    stack trace.
    """
    if not isinstance(raw, str) or not raw:
        return None
    if len(raw.encode("utf-8", errors="ignore")) > MAX_STAMP_BYTES:
        _log.warning("resume_stamp_oversized", size=len(raw))
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # A PDF whose keywords field holds ordinary keywords, which is what
        # that field is FOR. Not an error, just not ours.
        return None
    if not isinstance(data, dict):
        return None

    version = data.get("v")
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    if version != STAMP_VERSION:
        # Decline rather than guess. A future stamp may mean something
        # different by the same keys, and a half-understood resume silently
        # drops the client's work.
        _log.info("resume_stamp_version_unknown", version=version)
        return None

    fsid = data.get("fsid")
    if not isinstance(fsid, str) or not fsid:
        return None
    # THE STAMPED ID REACHES A FILENAME. confirmation_logger writes a
    # per-session file named from form_session_id, so a hand-edited PDF
    # carrying "../../../etc/passwd" must be refused HERE rather than
    # sanitised downstream. Reuse that module's guard rather than writing a
    # second one: it was hardened adversarially (Windows device names,
    # trailing dots -- both passed its first version), and a second copy would
    # drift from it.
    from backend.utils.confirmation_logger import _is_safe_session_id

    if not _is_safe_session_id(fsid):
        _log.warning("resume_stamp_unsafe_session_id")
        return None

    out: dict[str, Any] = {"v": version, "fsid": fsid}

    kit = data.get("kit")
    if isinstance(kit, str) and kit:
        out["kit"] = kit

    sv = data.get("sv")
    if isinstance(sv, str) and sv:
        out["sv"] = sv

    jtis = data.get("jtis")
    if isinstance(jtis, list):
        clean = [j for j in jtis if isinstance(j, str) and j]
        if clean:
            out["jtis"] = clean

    return out
