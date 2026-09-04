"""ONE image, TWO Cloud Run services, selected at RUNTIME (bd polyglot-pdf-pnoik).

The root Dockerfile is built by deploy-all.sh with `gcloud builds submit --tag`,
which CANNOT pass `--build-arg`. So the ASGI target cannot be baked in at build
time without building a second image per service. Instead the CMD reads
`${APP_MODULE:-backend.main:app}`, which a `gcloud run deploy --set-env-vars`
block can override per service.

NOTHING SETS IT YET. No deploy script on this branch passes APP_MODULE, so
every service built from this image serves the default today. The admin deploy
script lands with sprint-22 plan bead 1.3; the consumer side ships first so
that deploy is a config change, not a code change. That "no producer yet" state
is itself pinned below, so the docs describing it cannot quietly go stale the
day the producer appears.

Three properties this pins, each of which breaks a deploy if it drifts:

  1. The CMD honors APP_MODULE at all. Hardcode `backend.main:app` back into
     the CMD and the admin service silently serves the PUBLIC app -- on the
     wide service account, with none of the admin routes present, and a
     /health that looks perfectly fine.
  2. The default is the public backend. Change or drop it and every existing
     deploy that sets nothing (the demo and staging both predate APP_MODULE)
     starts serving the wrong app, or fails to start at all.
  3. No build arg was introduced. An `ARG APP_MODULE` reads as equivalent and
     is not: `gcloud builds submit --tag` has no way to set it, so the value
     would freeze at its default while the deploy-time env var is ignored.

Also pins that admin_backend/ is actually COPIED into the image -- an APP_MODULE
pointing at a package the image does not contain is a container that crash-loops
on start, which is a deploy-only failure no unit test would otherwise see.

Mutations that must turn this red:
  - CMD uvicorn backend.main:app ...            (property 1)
  - CMD uvicorn ${APP_MODULE:-admin_backend.main:app} ...   (property 2)
  - ARG APP_MODULE=backend.main:app             (property 3)
  - deleting COPY admin_backend /app/admin_backend
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"

# The default the CMD must fall back to, and the module admin_backend/main.py
# declares as DEFAULT_APP_MODULE. One string, asserted equal in both places
# below, so the container's fallback and the app's self-report cannot drift.
DEFAULT_APP_MODULE = "backend.main:app"
ADMIN_APP_MODULE = "admin_backend.main:app"


def _dockerfile_lines() -> list:
    """Non-comment, non-blank Dockerfile lines.

    Comments are stripped so a mention of ARG or APP_MODULE in the explanatory
    prose above the CMD (there is a lot of it) can never satisfy -- or trip --
    an assertion about the instructions themselves. That is the exact failure
    shape tests/test_technical_guide_routes_table.py's parser kept hitting:
    drawing a claim from text that was not the claim.
    """
    out = []
    for raw in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _cmd_line() -> str:
    cmds = [l for l in _dockerfile_lines() if l.startswith("CMD ")]
    assert len(cmds) == 1, (
        "expected exactly one CMD instruction in the Dockerfile, found "
        "{}: {}".format(len(cmds), cmds))
    return cmds[0]


def test_the_cmd_reads_app_module_from_the_runtime_environment():
    """Property 1: the ASGI target is a runtime variable, not a literal."""
    cmd = _cmd_line()
    assert "${APP_MODULE" in cmd, (
        "the Dockerfile CMD does not read APP_MODULE, so the shared image "
        "cannot serve the admin service:" + chr(10) + "  " + cmd)
    # Shell form, not exec form: `CMD ["uvicorn", "${APP_MODULE}"]` performs NO
    # variable expansion at all -- uvicorn would be handed the literal string.
    assert not cmd.startswith("CMD ["), (
        "the CMD is in EXEC form, which does no shell expansion: "
        "${APP_MODULE} and ${PORT} would both be passed as literal text."
        + chr(10) + "  " + cmd)


def test_the_cmd_default_is_the_public_backend():
    """Property 2: an unset (or empty) APP_MODULE serves what it always did."""
    cmd = _cmd_line()
    match = re.search(r"\$\{APP_MODULE:-([^}]+)\}", cmd)
    assert match, (
        "the CMD reads APP_MODULE without a `:-` default. Every existing "
        "deploy sets no APP_MODULE, so an unset value must fall back to "
        "{}:".format(DEFAULT_APP_MODULE) + chr(10) + "  " + cmd)
    assert match.group(1) == DEFAULT_APP_MODULE, (
        "the CMD default is {!r}, expected {!r}. Existing deploys pass no "
        "APP_MODULE at all.".format(match.group(1), DEFAULT_APP_MODULE))
    # `:-` (unset OR empty) rather than `-` (unset only): a deploy that passes
    # APP_MODULE= would otherwise hand uvicorn an empty target and crash-loop.
    assert "${APP_MODULE:-" in cmd, cmd


def test_no_build_arg_was_introduced_for_the_app_module():
    """Property 3: deploy-all.sh cannot pass --build-arg, so none may exist.

    `gcloud builds submit --tag <image> <dir>` builds with no way to set a
    build ARG. An ARG here would freeze at its default in every image while
    the deploy-time --set-env-vars value is silently ignored.
    """
    args = [l for l in _dockerfile_lines() if l.startswith("ARG ")]
    assert not args, (
        "the Dockerfile declares build ARGs, which deploy-all.sh's "
        "`gcloud builds submit --tag` cannot set:"
        + chr(10) + "  " + (chr(10) + "  ").join(args))


def test_no_env_default_masks_the_cmd_fallback():
    """An `ENV APP_MODULE=...` would make the `:-` fallback dead code.

    Worse, it hides the empty-string case: with an ENV default, a deploy that
    passes APP_MODULE= (a real shape when a bash variable is unset in a
    --set-env-vars block) overrides the ENV with empty, the `:-` never fires
    because the variable IS set, and the container crash-loops.
    """
    envs = [l for l in _dockerfile_lines()
            if l.startswith("ENV ") and "APP_MODULE" in l]
    assert not envs, (
        "APP_MODULE has an ENV default, which makes the CMD's `:-` fallback "
        "unreachable:" + chr(10) + "  " + (chr(10) + "  ").join(envs))


def test_both_packages_are_copied_into_the_image():
    """APP_MODULE can only point at a package the image actually contains."""
    copies = [l for l in _dockerfile_lines() if l.startswith("COPY ")]
    joined = chr(10).join(copies)
    assert re.search(r"^COPY\s+backend\s+/app/backend$", joined, re.MULTILINE), (
        "the public backend package is not copied into the image:"
        + chr(10) + joined)
    assert re.search(
        r"^COPY\s+admin_backend\s+/app/admin_backend$", joined, re.MULTILINE), (
        "admin_backend/ is not copied into the image, so a service deployed "
        "with APP_MODULE={} crash-loops on start:".format(ADMIN_APP_MODULE)
        + chr(10) + joined)


def test_the_admin_app_declares_the_same_default_as_the_dockerfile():
    """The container's fallback and the app's self-report are ONE string.

    admin_backend/main.py reports the active module on /health so an operator
    can confirm which app a service is really serving. If its default and the
    Dockerfile's diverge, that report lies in exactly the case it exists to
    catch.
    """
    from admin_backend.main import DEFAULT_APP_MODULE as app_default

    match = re.search(r"\$\{APP_MODULE:-([^}]+)\}", _cmd_line())
    assert match
    assert app_default == match.group(1) == DEFAULT_APP_MODULE, (
        "admin_backend.main.DEFAULT_APP_MODULE is {!r} but the Dockerfile "
        "CMD falls back to {!r}".format(app_default, match.group(1)))


def test_the_two_app_module_readers_agree_on_every_env_state(monkeypatch):
    """Agreement on the DEFAULT STRING is not agreement on BEHAVIOR.

    The test above pins one string in two places, which reads as stronger than
    it is: it says nothing about how each reader treats an EMPTY value. The
    Dockerfile's `${APP_MODULE:-...}` is the `:-` form (unset OR empty both
    fall back); a plain os.getenv(name, default) falls back only on unset.
    Those disagree precisely when an operator's --set-env-vars block passes
    APP_MODULE= -- so pin all three states against a model of the shell
    expansion rather than trusting the shared literal.
    """
    from admin_backend.main import _active_app_module

    default = re.search(r"\$\{APP_MODULE:-([^}]+)\}", _cmd_line()).group(1)

    def shell_expansion(value):
        """`${APP_MODULE:-default}` -- ':-' falls back on unset AND empty."""
        return value if value else default

    for state, value in (("unset", None), ("empty", ""),
                         ("set", ADMIN_APP_MODULE)):
        if value is None:
            monkeypatch.delenv("APP_MODULE", raising=False)
        else:
            monkeypatch.setenv("APP_MODULE", value)
        assert _active_app_module() == shell_expansion(value), (
            "with APP_MODULE {}, the app reports {!r} but the container would "
            "launch {!r}".format(state, _active_app_module(),
                                 shell_expansion(value)))


# The docs that describe WHO sets APP_MODULE. Each is a tier-1/tier-2 doc or a
# module docstring that a reader (or a cross-surface reviewer tracing the
# contract) treats as current state, so each must agree with the deploy scripts
# about whether a producer exists at all.
_PRODUCER_CLAIM_SITES = (
    "docs/technical_guide.md",
    "docs/components/config-deployment.md",
    "admin_backend/__init__.py",
    "Dockerfile",
)


def _deploy_scripts() -> list:
    """Every deploy script that could set APP_MODULE, derived from the repo.

    Globbed, not hand-listed: a NEW deploy script is exactly the event that
    turns "no producer" into "a producer", and a hand-written list would miss
    the one file that matters.
    """
    scripts = sorted(REPO_ROOT.glob("deploy-*.sh"))
    scripts += sorted(REPO_ROOT.glob("backend/deploy-*.sh"))
    scripts += sorted(REPO_ROOT.glob("scripts/deploy-*.sh"))
    assert scripts, "no deploy-*.sh scripts found -- has the layout changed?"
    return scripts


def test_docs_do_not_claim_a_live_app_module_producer_while_none_exists():
    """The Surface-contracts map must not name a PRODUCER that sets nothing.

    docs/technical_guide.md's Surface contracts section declares itself derived
    from code, with the producer and consumer code site for each contract -- it
    is the blast-radius map a cross-surface reviewer is told to trace from. A
    row naming `deploy-all.sh` as the APP_MODULE producer sends that reviewer
    to a file containing no such assignment.

    This pins the AGREEMENT rather than the current answer, so it stays correct
    in both directions: while no deploy script assigns APP_MODULE, no doc may
    assert one does; the day bead 1.3's deploy script lands, this test flips
    and REQUIRES the docs to be updated to match. Either way the docs cannot
    silently disagree with the scripts.

    Mutation: write "the admin service is deployed with APP_MODULE=..." into
    any listed doc while no script sets it -- red.
    """
    producers = []
    for script in _deploy_scripts():
        text = script.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"\bAPP_MODULE\s*=", stripped):
                producers.append("{}:{}".format(
                    script.relative_to(REPO_ROOT).as_posix(), lineno))

    # A doc claims a live producer when it says the admin service IS deployed
    # with the variable, in the present tense. The hedged forward-looking forms
    # ("will run", "lands with", "NONE YET") are what correctness looks like
    # while the producer is absent, so they must not match.
    present_tense = re.compile(
        r"(?:is|are)\s+deployed\s+with\s+`?APP_MODULE"
        r"|APP_MODULE\s+rides\s+in\s+through[^.]*\bso\s+one\s+image\s+backs\b"
        r"|admin\s+service\s+is\s+deployed\s+with",
        re.IGNORECASE)

    offenders = []
    for rel in _PRODUCER_CLAIM_SITES:
        path = REPO_ROOT / rel
        assert path.exists(), "pinned producer-claim site is missing: " + rel
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if present_tense.search(line):
                offenders.append("{}:{}: {}".format(rel, lineno, line.strip()))

    if producers:
        # A producer exists now -- the docs SHOULD describe it, and the
        # "NONE YET" wording this branch shipped is what is now stale.
        stale = []
        for rel in _PRODUCER_CLAIM_SITES:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8",
                                               errors="replace")
            if "NONE YET" in text or "NOTHING SETS IT YET" in text:
                stale.append(rel)
        assert not stale, (
            "a deploy script now SETS APP_MODULE ({}), but these docs still "
            "say no producer exists:\n  {}\n\nUpdate them to name the real "
            "producer.".format(", ".join(producers), "\n  ".join(stale)))
        return

    assert not offenders, (
        "no deploy script assigns APP_MODULE (checked {} scripts), but these "
        "docs claim a live producer:\n  ".format(len(_deploy_scripts()))
        + "\n  ".join(offenders)
        + "\n\nDescribe the producer in the FUTURE tense until the deploy "
          "script that sets it actually lands.")


def test_the_admin_module_path_is_importable_as_written():
    """`admin_backend.main:app` is a real module:attribute pair.

    A typo here is a deploy-only failure: the image builds, the deploy
    succeeds, and the container exits on start.
    """
    import importlib

    module_path, _, attr = ADMIN_APP_MODULE.partition(":")
    module = importlib.import_module(module_path)
    assert hasattr(module, attr), (
        "{} has no attribute {!r}".format(module_path, attr))
