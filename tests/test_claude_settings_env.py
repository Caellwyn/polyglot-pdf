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

# Both are tracked in this repo, so both ship to everyone.
SHARED_SETTINGS = [
    REPO_ROOT / ".claude" / "settings.json",
    REPO_ROOT / ".claude" / "settings.local.json",
]

# A Windows drive-letter path ("C:\..." or "C:/...") anywhere in a value.
_DRIVE_LETTER_RE = re.compile(r"[A-Za-z]:[\\/]")
# An MSYS/Git-Bash drive path ("/c/Users/...") -- resolves in bash, but NOT for
# a Windows-native process, so it is the trap that looks portable and is not.
_MSYS_DRIVE_RE = re.compile(r"(?:^|[:;])/[A-Za-z]/")
# A home directory spelled out rather than derived.
_LITERAL_HOME_RE = re.compile(r"(?:[\\/](?:Users|home)[\\/])(?!\$)[A-Za-z0-9_.-]+")


def _settings_files():
    return [p for p in SHARED_SETTINGS if p.is_file()]


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
    offenders = []
    for path, key, value in _env_items():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _DRIVE_LETTER_RE.search(value):
            offenders.append(f"{rel}: env.{key} has a drive-letter path: {value!r}")
        elif _MSYS_DRIVE_RE.search(value):
            offenders.append(f"{rel}: env.{key} has an MSYS /c/ path: {value!r}")
        elif _LITERAL_HOME_RE.search(value):
            offenders.append(f"{rel}: env.{key} hardcodes a home dir: {value!r}")
    assert not offenders, (
        "Tracked settings env values contain machine-specific absolute paths, "
        "which are wrong for every other contributor (bd polyglot-pdf-6peeg / "
        "polyglot-pdf-enot7):\n  " + "\n  ".join(offenders)
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
