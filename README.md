# Daybook

A personal task notebook based on Avi’s Notes workflow. Manually add tasks at the top, check them off, and let Daybook keep a dated **DAY DONE** history.

## Mac app

Download `Daybook-1.0.0-universal.dmg` from this private repository’s Releases, open it, and drag **Daybook** into **Applications**. It runs offline without Python, Node, a browser, or a local server.

- Requires macOS 13 or later. The universal executable includes Apple silicon and Intel architectures.
- This personal build is **ad-hoc signed, not Apple-notarized**. macOS may ask you to approve the first launch in System Settings → Privacy & Security.
- The app stores its notebook in `~/Library/Application Support/Daybook/notebook.json`. Writes replace the file atomically; failed writes are reported in the app.
- Use **Back up notebook** to save a timestamped JSON copy in `~/Library/Application Support/Daybook/Backups/` and reveal it in Finder. Move that copy to another drive or folder if desired. Browser and native notebooks are separate. This version does not yet offer an in-app backup restore screen.
- The app contains no external integrations and sends no task data to a server.

## Workflow

- Enter tasks at the top. Newest-first is the default; Suggested and Due date ordering are optional.
- Add details for category, due date (Today/Tomorrow/In a week shortcuts), quiet importance, recurrence, and optional effort.
- Check a task to move it into dated DAY DONE history. Undo, or click its check in history, to reopen it.
- Everyday and weekly repeats create one future occurrence, measured from the completion day. Missed days do not create duplicate backlogs. Future repeats cannot be completed early; edit their date to change the schedule.
- Weekly review shows daily completions, category totals, unfinished and overdue work, estimated completed effort, and daily backlog. Today is partial. Future days have no backlog value, and future repeats are excluded from current unfinished counts.
- Observations describe recorded activity without treating quiet days as poor productivity. Effort is an estimate, not tracked time.

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
```

The builder compiles both architectures, bundles the web UI into one offline document, generates the icon, applies an ad-hoc signature, creates the DMG, and verifies the image. Build products are ignored by Git and attached to the release.

Core tests cover dates, validation, completion/reopen, recurrence, suggestions, weekly calculations, and idempotent screenshot import. Manual checks cover the browser and native app.

## Implementation

- `dist/`: browser application, shared task logic, and screenshot import.
- `macos/Daybook.swift`: AppKit/WebKit shell, atomic notebook persistence, and native backup export.
- `macos/Icon.swift`: application icon renderer.
- `scripts/build-mac.py`: reproducible universal app and DMG build.
- `tests/`: model and import tests.

Backlog is reconstructed from created/completed/deleted dates. Editing a schedule or reopening an older task can revise historical unfinished counts; this is not an immutable event ledger.
