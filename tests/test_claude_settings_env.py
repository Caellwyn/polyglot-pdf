"""The SHARED .claude/settings.json must not carry machine- or OS-specific env.

WHY THIS FILE EXISTS (bd polyglot-pdf-6peeg). `.claude/settings.json` is
TRACKED, so every value in it ships to every contributor on every OS. An `env`
block was added there to make `bd` resolve to the native `bd.exe` instead of
npm's POSIX-shell shim:

    "env": {"PATH": "C:\\\\Users\\\\caell\\\\...\\\\@beads\\\\bd\\\\bin;${PATH}"}

On Windows that works. On macOS/Linux it is not an inert bogus entry -- it
CORRUPTS PATH. POSIX splits on ":", so the expanded value yields the fields
'C', '\\Users\\caell\\...\\bd\\bin;/usr/local/bin', '/usr/bin' -- and
/usr/local/bin, where Homebrew/npm put `bd`, `gh` and `node`, stops being a
searchable entry. The override meant to FIX bd resolution would break bd and gh
on the platforms it was never aimed at.

THERE IS NO CORRECT SINGLE STRING, which is why this is a ban and not a
lint-and-repair:
  - ";" breaks POSIX (above);
  - ":" breaks Windows -- the "C:" drive letter splits into its own field;
  - the MSYS form ("/c/Users/...") resolves in Git Bash but NOT for a
    Windows-native process (verified: shutil.which returns None for it), so it
    silently breaks every Python caller;
  - Claude Code settings support no OS conditionals, and `.claude/
    settings.local.json` is ALSO tracked in this repo, so it is not a
    machine-local escape hatch.

The fix is to put such a path in the developer's own persistent user PATH,
where it is machine-local and separator-native by construction, and keep the
shared file OS-agnostic. `scripts/swarm_config.py` does the in-process
equivalent correctly and is the model: derive from expanduser("~"), guard on
the file existing, and join with os.pathsep.

SCOPE is the shared settings files only. A developer's own untracked config is
their business; this pins what the REPO ships.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# EVERY tracked JSON under .claude/ ships to everyone, so the scope is derived
# by GLOB rather than hand-listed: a new tracked config is covered the day it
# appears, instead of the day someone remembers to add it here. (The first
# version listed settings.json + settings.local.json and silently omitted
# launch.json -- exactly the omission scar tissue #8 is about.)
def _shared_settings_files():
    return sorted((REPO_ROOT / ".claude").glob("*.json"))


# An ALLOWLIST of value shapes that are safe to ship in a tracked config.
# Deliberately an allowlist, not a blacklist of bad paths: a blacklist is
# always one unenumerated spelling from being defeated, and the first draft of
# this file proved it -- "%APPDATA%\npm\..." and "/opt/homebrew/bin" both slipped
# past three hand-written "looks machine-specific" patterns (found by the
# fresh-eyes reviewer). What makes a value SAFE is positive and short to state:
# it must not name an absolute location on somebody's disk.
#
# Safe: a bare token ("1", "true", "dev"), or a value built only from
# ${VAR} interpolation plus separators/relative fragments.
_ABSOLUTE_PATH_RE = re.compile(
    r"""(?x)
    [A-Za-z]:[\\/]          # C:\ or C:/            -- Windows drive letter
  | (?:^|[:;])/[A-Za-z]/    # /c/...                -- MSYS drive path
  | (?:^|[:;])/[A-Za-z]     # /usr, /opt, /Users... -- POSIX absolute path
  | %[A-Za-z_][A-Za-z0-9_]*%  # %APPDATA%           -- Windows env-var ref
    """
)


def _settings_files():
    return [p for p in _shared_settings_files() if p.is_file()]


def _env_items():
    """Yield (path, key, value) for every env entry in the shared settings."""
    for path in _settings_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        env = data.get("env")
        if not isinstance(env, dict):
            continue
        for key, value in env.items():
            if isinstance(value, str):
                yield path, key, value


def test_shared_settings_declare_no_path_env():
    """No PATH override in a TRACKED settings file -- it cannot be OS-correct.

    This is the direct bd polyglot-pdf-6peeg regression pin. PATH is singled
    out because it is the one variable whose SEPARATOR differs by OS, so a
    single literal is wrong on one platform by construction.
    """
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()}: env.{key} = {value!r}"
        for path, key, value in _env_items()
        if key.upper() == "PATH"
    ]
    assert not offenders, (
        "A tracked settings file sets env.PATH. There is no separator that is "
        "correct on both Windows (';') and POSIX (':'), so this value is wrong "
        "on one platform by construction and can DROP a real PATH entry there "
        "(bd polyglot-pdf-6peeg):\n  "
        + "\n  ".join(offenders)
        + "\n\nPut the directory in your own persistent user PATH instead, and "
        "keep the shared file OS-agnostic."
    )


def test_shared_settings_env_has_no_machine_specific_paths():
    """No absolute machine paths in a tracked env block, whatever the key.

    Pins the CLASS, not just PATH (scar tissue #8): a hardcoded
    `C:\\Users\\<name>\\...` in any env value is broken for every other
    contributor, and an MSYS `/c/...` value is worse -- it works in bash and
    silently fails for Windows-native processes, so it looks portable while
    not being so.
    """
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()}: env.{key} = {value!r}"
        for path, key, value in _env_items()
        if _ABSOLUTE_PATH_RE.search(value)
    ]
    assert not offenders, (
        "Tracked settings env values name an absolute location on somebody's "
        "disk, which is wrong for every other contributor (bd "
        "polyglot-pdf-6peeg / polyglot-pdf-enot7):\n  "
        + "\n  ".join(offenders)
        + "\n\nBuild the value from ${VAR} interpolation, or set it in your own "
        "machine-local environment instead of the shared config."
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(r"C:\Users\caell\npm\bd\bin", id="windows-drive-letter"),
        pytest.param("C:/Users/caell/npm/bd/bin", id="windows-forward-slash"),
        pytest.param("/c/Users/caell/npm/bd/bin", id="msys-drive-path"),
        pytest.param("/Users/someone/bin", id="macos-home"),
        pytest.param("/home/someone/bin", id="linux-home"),
        # The two that defeated the first draft's hand-written patterns. They
        # are parametrized BY NAME so a future narrowing of the regex fails
        # here loudly rather than silently reopening the hole.
        pytest.param(r"%APPDATA%\npm\node_modules\@beads\bd\bin", id="win-envvar-ref"),
        pytest.param("/opt/homebrew/bin", id="posix-abs-no-home-segment"),
        pytest.param("/usr/local/bin:${PATH}", id="posix-abs-with-interpolation"),
    ],
)
def test_machine_specific_shapes_are_all_rejected(value):
    """Every known machine-specific spelling is caught, not just the obvious ones.

    A blacklist is one unenumerated spelling from being defeated -- which is
    not hypothetical here: the first draft of this file missed `%APPDATA%\\...`
    and `/opt/homebrew/bin`, both found by review. These cases pin the ones we
    know about so a future edit to the pattern cannot quietly drop one.
    """
    assert _ABSOLUTE_PATH_RE.search(value), (
        f"{value!r} names an absolute machine location but is NOT rejected -- "
        f"the guard has a hole"
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("${PATH}", id="pure-interpolation"),
        pytest.param("1", id="bare-flag"),
        pytest.param("true", id="bare-bool"),
        pytest.param("${CLAUDE_PROJECT_DIR}/scripts", id="interpolated-relative"),
        pytest.param("dev", id="bare-word"),
    ],
)
def test_portable_values_are_not_rejected(value):
    """The guard does not reject legitimate portable values.

    Without this, tightening the pattern until it rejects everything would
    look like a passing guard while banning every usable config value.
    """
    assert not _ABSOLUTE_PATH_RE.search(value), (
        f"{value!r} is portable but the guard rejects it -- too strict"
    )


@pytest.mark.parametrize("sep", [";", ":"])
def test_no_separator_choice_would_have_been_safe(sep):
    """The ban is justified: BOTH separators corrupt one platform.

    Not a guard on repo state -- it pins the REASONING, so a future reader who
    wants to "just fix the separator" can see, mechanically, that neither
    choice works. If this ever fails, the premise changed and the ban above
    deserves revisiting.
    """
    win_dir = r"C:\Users\someone\AppData\Roaming\npm\node_modules\@beads\bd\bin"
    posix_entries = ["/usr/local/bin", "/usr/bin", "/bin"]
    value = win_dir + sep + ":".join(posix_entries)

    if sep == ";":
        # POSIX splits on ":" -- the first real entry gets swallowed into the
        # Windows path's field and stops being searchable.
        fields = value.split(":")
        assert "/usr/local/bin" not in fields, (
            "expected ';' to corrupt the POSIX split, but /usr/local/bin "
            "survived as its own field -- the premise of this ban changed"
        )
    else:
        # ":" keeps POSIX intact but destroys the Windows path: the drive
        # letter becomes its own field and the directory is unreachable.
        fields = value.split(":")
        assert "C" in fields and win_dir not in fields, (
            "expected ':' to split the Windows drive letter, but the path "
            "survived intact -- the premise of this ban changed"
        )
