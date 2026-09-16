"""Regenerate frontend/public/fonts from Google Fonts, in-process.

Fetches the css2 stylesheet for the app's two families with a modern browser
UA (so the woff2 unicode-range subsets come back), keeps every unicode-range
subset Google serves, downloads each woff2 next to this stylesheet's output, and
rewrites the @font-face url()s to /fonts/<family>-<weight>-<subset>.woff2.
No subprocess, no gcloud: urllib only (sprint 23 E2, bd polyglot-pdf-j29z1).

Usage:  python scripts/fetch_fonts.py            (from the repo root)
"""
from __future__ import annotations

import io
import os
import re
import sys
import urllib.request

FAMILIES = "family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700"
CSS_URL = "https://fonts.googleapis.com/css2?" + FAMILIES + "&display=swap"
# Every subset Google serves for these families: the app's UI is translated
# into languages that use Cyrillic, Greek and Vietnamese script, and those
# users got these glyphs from Google before; self-hosting must not regress them.
SUBSETS = ("latin", "latin-ext", "cyrillic", "cyrillic-ext", "greek", "greek-ext", "vietnamese")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "frontend", "public", "fonts")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=60).read()


def main() -> int:
    css = _get(CSS_URL).decode("utf-8")
    blocks = re.findall(r"/\* (\w[\w-]*) \*/\s*(@font-face \{.*?\})", css, re.S)
    if not blocks:
        print("no @font-face blocks came back; is the UA still modern enough?", file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    out = [
        "/* Self-hosted Inter + Outfit (every subset Google serves), fetched from Google Fonts",
        " * once and served from this origin so no third-party font host is",
        " * contacted (sprint 23 E2, bd polyglot-pdf-j29z1). Regenerate with",
        " * scripts/fetch_fonts.py. */",
        "",
    ]
    n = 0
    for subset, block in blocks:
        if subset not in SUBSETS:
            continue
        family = re.search(r"font-family: '([^']+)'", block).group(1)
        weight = re.search(r"font-weight: (\d+)", block).group(1)
        url = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", block).group(1)
        name = "%s-%s-%s.woff2" % (family.lower(), weight, subset)
        with open(os.path.join(OUT_DIR, name), "wb") as f:
            f.write(_get(url))
        n += 1
        out += ["/* %s */" % subset, block.replace(url, "/fonts/" + name), ""]
    io.open(os.path.join(OUT_DIR, "fonts.css"), "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("wrote %d woff2 files + fonts.css under %s" % (n, OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
