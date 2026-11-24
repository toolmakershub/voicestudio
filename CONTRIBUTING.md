# Contributing to ToolMakersHub Voice Studio

Thanks for helping! There are three ways to contribute, and only one of them needs code.

## 1. Share an idea (no code needed)
A new language, a voice, a feature or a fix: send it at **https://voice.toolmakershub.com/#ideas**.
Sign in with a free ToolMakersHub account to follow it on "My ideas". If we build it and you agree,
your name goes on the contributors list on voice.toolmakershub.com and toolmakershub.com/contributors.

## 2. Report a bug
Open a [GitHub issue](https://github.com/toolmakershub/voicestudio/issues) with:
- what you did, what you expected, and what happened
- Windows version, graphics card (GPU) and Voice Studio version (shown in the studio header)
- the error message or the console output, if any

Please **don't** attach voice samples of other people or private scripts.

## 3. Send code, docs or translations
1. Fork the repository and create a branch from `main` (e.g. `fix/tamil-dates`).
2. Keep changes focused; one topic per pull request.
3. Test what you changed: run the studio (`run.bat`), or for Lite `lite\run_lite.bat`.
4. Add a line under **## Unreleased** in `CHANGELOG.md` if users would notice the change.
5. Open a pull request and tick **"I agree to the CLA"** (see [CLA.md](CLA.md)). We can't merge without it.

### Ground rules
- No model weights, voice samples, generated audio, tokens or `.env` files in commits (see `.gitignore`).
- Voice cloning must keep its consent check. Pull requests that remove or weaken it won't be merged.
- New dependencies must have a licence compatible with AGPL-3.0 (MIT, BSD, Apache-2.0, GPL-3.0, AGPL-3.0…).
- Be kind. We follow the spirit of the [Contributor Covenant](https://www.contributor-covenant.org/).

## Licence
Voice Studio is licensed under the **GNU Affero General Public License v3.0** ([LICENSE](LICENSE)).
If you run a modified version for others over a network, you must offer them its source code.
For a commercial licence, contact hello@toolmakershub.com.
