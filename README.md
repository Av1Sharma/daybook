# Daybook

A personal task notebook based on Avi’s Notes workflow. Manually add tasks at the top, check them off, and let Daybook keep a dated **DAY DONE** history.

## Mac app

Download `Daybook-1.2.0-universal.dmg` from this private repository’s Releases, open it, and drag **Daybook** into **Applications**. It runs offline without Python, Node, a browser, or a local server.

- Requires macOS 13 or later. The universal executable includes Apple silicon and Intel architectures.
- This personal build is **ad-hoc signed, not Apple-notarized**. macOS may ask you to approve the first launch in System Settings → Privacy & Security.
- The app stores its notebook in `~/Library/Application Support/Daybook/notebook.json`. Writes replace the file atomically; failed writes are reported in the app.
- Use **Back up notebook** to save a timestamped JSON copy in `~/Library/Application Support/Daybook/Backups/` and reveal it in Finder. Move that copy to another drive or folder if desired. Browser and native notebooks are separate. This version does not yet offer an in-app backup restore screen.
- Task data stays on your Mac. The updater contacts GitHub only for release metadata and app downloads.

## Automatic app updates

Install 1.2.0 manually once; older releases have no updater. After that, Daybook checks its private GitHub releases shortly after launch and every six hours. Choose **Install & Relaunch** to download, verify, and replace the app. **Later** defers the prompt for 24 hours. The Daybook menu also offers **Check for Updates…** and a toggle for automatic checks.

Private downloads use the GitHub CLI (`gh`) already installed and signed in on Avi’s Mac. Other Macs need GitHub CLI from cli.github.com and `gh auth login` with access to this private repository. No token is embedded in Daybook. A failed automatic check stays quiet; a manual check explains the failure. Task features work offline without GitHub CLI.

Updates require a writable app folder, not a mounted DMG. The app verifies an Ed25519-signed manifest, archive size and SHA-256 hash, version, bundle identity, and code signature before installation. The installer preserves the old bundle as a hidden sibling `.Daybook.previous-…app` and restores it if replacement or its launch command fails. It never replaces your notebook file. This release signature is separate from Apple notarization; this remains an ad-hoc signed personal app.

## Workflow

- Enter tasks at the top. Newest-first is the default; Suggested and Due date ordering are optional.
- Add details for category, due date (Today/Tomorrow/In a week shortcuts), quiet importance, recurrence, and optional effort.
- Check a task to move it into dated DAY DONE history. Undo, or click its check in history, to reopen it.
- Everyday and weekly repeats create one future occurrence, measured from the completion day. Missed days do not create duplicate backlogs. Future repeats cannot be completed early; edit their date to change the schedule.
- Weekly review shows daily completions, category totals, unfinished and overdue work, estimated completed effort, and daily backlog. Today is partial. Future days have no backlog value, and future repeats are excluded from current unfinished counts.
- Observations describe recorded activity without treating quiet days as poor productivity. Effort is an estimate, not tracked time.

## Internship reminders

Company names and search ideas live in the **Internship reminders** tab, together with application history and target-company reference lists. They are not open tasks and do not add to overdue/backlog totals. Actual online assessments (Johnson Johnson, Parsons, P&G) remain in **My day**.

There are exactly three named reminder check-ins. Rename them to match the three existing ChatGPT reminders. Read a reminder in ChatGPT, apply to the relevant roles, and check it off in Daybook. Check-offs are recorded in DAY DONE and weekly totals. Choose **Ready for next reminder** when the next notification arrives; this keeps the previous completion in history. No notification schedules are invented, and no new ChatGPT reminders are created.

The upgrade preserves existing tasks and history, moves the five imported company/search items to reference material, and replaces the generic “Spam Jobs” routine with the three check-ins. It leaves nine original actionable tasks in My day, including all three OAs. The migration runs once per notebook.

## Screenshot import

The five supplied screenshots are imported once, preserving existing notebook entries:

- **15 open tasks**, including two Everyday routines.
- **62 dated completion entries**, across August 24–September 23, 2026.
- **7 undated completion entries**, kept in Reference notes rather than assigned an invented date.
- **21 application entries**, including their role/location notes.
- **26 target companies** and the **3 original project ideas**.

The screenshot timestamp supplies the year 2026. “Monday” and “Friday” remain notes until an exact deadline is chosen. Imported completions display their day without an invented time. Creation dates were not recorded, so imports do not count as newly added work. Missing history and earlier workload counts remain incomplete. Company availability notes are historical screenshot text, not verified current job listings.

## Browser version

Double-click `Start Daybook.command` on a Mac with Python 3, or run:

```sh
python3 -m http.server 4173 --directory dist
```

Open `http://localhost:4173`. Use the same browser and address each time. Browser data is in localStorage under `daybook.notebook.v1`; clearing site data removes it. The native app uses its own file and does not share browser localStorage.

## Build and test

Requires Apple command-line developer tools (Swift, SDK, codesign, hdiutil, iconutil, lipo), Python 3, and Node for the model tests.

```sh
node --test tests/*.test.mjs
python3 scripts/build-mac.py
swiftc -module-cache-path build/ModuleCache macos/Updates/UpdateCore.swift macos/Updates/UpdatePublicKey.swift macos/Updates/InstallCore.swift tests/UpdaterTests.swift -o build/updater-tests
build/updater-tests
```

The builder compiles both architectures, bundles the web UI into one offline document, generates the icon, applies an ad-hoc signature, creates the DMG, and verifies the image. Build products are ignored by Git and attached to the release. The builder also creates `Daybook-update.zip`, `daybook-update.json`, `daybook-update.sig`, and versioned checksums; attach all of these alongside the DMG to every release. The updater uses the newest published, non-prerelease `vX.Y.Z` release.

The release-signing private key lives only in the macOS Keychain, service `com.avisharma.daybook.release-signing`, account `ed25519-v1`. The public key is pinned in `macos/Updates/`. The build fails if that key is unavailable or mismatched; do not regenerate it for ordinary releases. Losing it requires a manual reinstall with a new trust key. `scripts/SignUpdate.swift initialize` was used only for initial setup.

Core tests cover dates, validation, completion/reopen, recurrence, suggestions, weekly calculations, and idempotent screenshot import. Manual checks cover the browser and native app.

## Implementation

- `dist/`: browser application, shared task logic, and screenshot import.
- `macos/Daybook.swift`: AppKit/WebKit shell, atomic notebook persistence, and native backup export.
- `macos/Icon.swift`: application icon renderer.
- `scripts/build-mac.py`: reproducible universal app and DMG build.
- `macos/Updates/`: private release checks, signature verification, and transactional installer.
- `tests/`: model/import tests plus native updater verification and rollback tests.

Backlog is reconstructed from created/completed/deleted dates. Editing a schedule or reopening an older task can revise historical unfinished counts; this is not an immutable event ledger.
