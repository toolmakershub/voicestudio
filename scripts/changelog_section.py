"""Print the CHANGELOG.md entry for one version, e.g.  python scripts/changelog_section.py v0.5.0

Exits with an error if the version has no entry, so a release can't go out without notes.
"""
import re
import sys
from pathlib import Path

tag = sys.argv[1].lstrip("v")
text = Path(__file__).resolve().parent.parent.joinpath("CHANGELOG.md").read_text(encoding="utf-8")
# Headings look like:  ## v0.5.0 — 2026-11-23
parts = re.split(r"(?m)^## ", text)
for part in parts[1:]:
    heading, _, body = part.partition("\n")
    if heading.split()[0].lstrip("v") == tag:
        print(body.strip())
        sys.exit(0)
sys.exit(f"CHANGELOG.md has no '## v{tag} — <date>' entry. Add one before releasing.")
