# Releasing Voice Studio

## Version numbers — `vMAJOR.MINOR.PATCH`
| Change | Bump | Example |
|---|---|---|
| Bug fix only | PATCH | v0.5.0 → v0.5.1 |
| New feature, nothing breaks | MINOR | v0.5.1 → v0.6.0 |
| Breaking change (setup must be redone, data format changes) | MAJOR | v1.4.2 → v2.0.0 |

Stay on `v0.x` while it is only for you; release `v1.0.0` when other people start using it.
`v0.x` releases and tags with a dash (e.g. `v0.6.0-beta.1`) are marked as pre-releases.

## Day to day
1. Work on a branch (e.g. `feature/tamil-dictionary`), merge into `main` when it works.
2. Add a line under **## Unreleased** in `CHANGELOG.md` for anything a user would notice.

`main` may hold unfinished work; only tagged releases are "official", and `update.bat` only moves to tags.

## Cutting a release (about 2 minutes)
1. In `CHANGELOG.md`, rename `## Unreleased` to `## v0.6.0 — YYYY-MM-DD` and add a new empty `## Unreleased` above it.
2. Put the same number, without the `v`, in `VERSION` (e.g. `0.6.0`).
3. Commit and push to `main`:
   ```
   git add CHANGELOG.md VERSION
   git commit -m "Release v0.6.0"
   git push origin main
   ```
4. Because `VERSION` changed, GitHub Actions (**Release** workflow):
   - stops if the changelog has no `## v0.6.0` entry,
   - creates the tag `v0.6.0` on that commit,
   - publishes a GitHub Release with the changelog entry as notes,
   - attaches `voicestudio-v0.6.0.zip` (full) and `voicestudio-lite-v0.6.0.zip` (Lite).

Check it under **Actions** and **Releases** on GitHub. If a release already exists for that version, the workflow does nothing.
(Pushing a `v0.6.0` tag yourself also works; it must match `VERSION`.)

## A release went wrong
Fix it on `main`, then release the next PATCH (e.g. `v0.6.1`). Don't move or reuse a tag that was already pushed: anyone who updated already has it.
