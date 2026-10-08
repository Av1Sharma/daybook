## Live demo and technology

[Open Daybook in your browser](https://av1sharma.github.io/daybook/). The browser edition keeps its notebook in that browser on your device; the separate Mac app can be installed from the Releases section below.

Daybook uses a shared web interface built with JavaScript and CSS, plus a small Swift shell for the macOS app. You can use the live browser demo right away, or install the native Mac app using the steps below.

# Daybook

A personal task notebook for macOS. Write down what needs doing, check it off, and keep a dated record of what you finished.

Daybook turns a simple Notes-style list into a daily workspace with recurring tasks, weekly reviews, and a separate place for internship reminders. Your notebook stays on your device, and the Mac app works offline.

## Install on macOS

1. Open this repository’s [Releases](https://github.com/Av1Sharma/daybook/releases).
2. Download `Daybook-1.2.0-universal.dmg`.
3. Open the disk image and drag **Daybook** into **Applications**.
4. Launch Daybook from Applications.

Requires **macOS 13 or later**. The universal app supports Apple silicon and Intel Macs. No Python, Node.js, browser, or local server is needed to use the installed app.

This personal build is ad-hoc signed and **not Apple-notarized**. macOS may require first-launch approval in **System Settings → Privacy & Security**.

## Use your notebook

| View | What it’s for |
| --- | --- |
| **My day** | Add, organize, and complete tasks. New tasks appear at the top by default. |
| **Day done** | Browse completed tasks by date. Reopen a task by clicking its checkmark. |
| **Weekly review** | Review completions, categories, unfinished work, overdue tasks, and estimated effort. |
| **Internship reminders** | Keep reusable application check-ins alongside company lists and application history. |
| **Reference notes** | Store context and undated notes without adding them to your task backlog. |

Tasks can have a category, due date, importance, repeat schedule, and effort estimate. Use **Today**, **Tomorrow**, or **In a week** for quick deadlines. Change the list order to **Suggested** or **Due date** when useful.

### Recurring tasks

Completing an everyday or weekly task creates one future occurrence, scheduled from the completion day. Missed days do not generate a backlog of duplicates. Future occurrences cannot be completed early; edit the date to change their schedule.

### Weekly review

Review totals describe the activity you recorded. Effort is an estimate, not a timer, and quiet days are not treated as poor productivity.

Today’s totals are partial. Future repeats are excluded from current unfinished counts, and future days have no backlog value. Backlog is reconstructed from task dates, so reopening a task or editing its schedule can change historical counts.

### Internship reminders

Three editable check-ins let you track action taken on your existing ChatGPT reminders. Rename each check-in to match its reminder, check it off after applying, and choose **Ready for next reminder** when the next notification arrives. Previous completions stay in Day done and weekly totals.

Daybook does not create or schedule ChatGPT notifications. Company lists and search ideas are reference material; actionable tasks such as online assessments stay in My day.

## Storage and backups

The Mac app saves its notebook here:

```text
~/Library/Application Support/Daybook/notebook.json
```

Saves replace the file atomically, and the app reports write failures. **Back up notebook** creates a timestamped JSON copy in the adjacent `Backups` folder and reveals it in Finder. Copy that backup to another drive or folder for an additional safeguard.

There is no in-app backup restore screen in version 1.2.0. App updates leave the notebook file untouched.

The native app and browser version keep **separate notebooks**. They do not sync with each other.

## App updates

Install version 1.2.0 manually once to enable the updater. Daybook then checks this private repository’s releases shortly after launch and every six hours.

- **Install & Relaunch** downloads and installs the update.
- **Later** postpones the prompt for 24 hours.
- The **Daybook** menu provides **Check for Updates…** and an automatic-checks toggle.

Private release downloads use an existing GitHub CLI (`gh`) sign-in with access to this repository. No token is embedded in the app. On another Mac, install GitHub CLI and run `gh auth login` to enable updates. Task features still work offline without it.

Automatic check failures stay quiet; manual checks explain failures. Install updates from a writable app folder, not a mounted disk image.

Before installation, Daybook verifies the signed update manifest, archive size and SHA-256 hash, version, bundle identity, and code signature. The installer keeps the previous app as a hidden sibling and restores it if replacement or the launch command fails. Update signing is separate from Apple notarization.

## Browser version

With Python 3 installed, double-click `Start Daybook.command`. Keep its terminal window open while using Daybook.

Alternatively, run this from the repository root:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist
```

Open `http://localhost:4173` and use the same browser and address each time. The notebook is stored in localStorage under `daybook.notebook.v1`. Clearing that site’s browser data removes its notebook.

## Imported history

This personal edition includes a one-time import from five Notes screenshots. It preserves existing notebook entries and includes tasks, dated completions, application notes, target companies, and project ideas.

Unknown dates remain unknown: undated completions stay in Reference notes, weekday-only deadlines remain notes, and imported completions do not receive invented times. Imported tasks have no recorded creation dates and do not count as newly added work. Company availability notes reflect the original screenshots, not live job listings.

The internship-reminder migration also runs once per notebook. It moves company/search items into reference material and replaces the old generic application routine with three reusable check-ins, preserving prior history.

## Development

The interface is shared between the browser app and an AppKit/WebKit macOS shell.

| Path | Contents |
| --- | --- |
| `dist/` | Browser interface, task logic, and import data; also bundled into the Mac app. |
| `macos/Daybook.swift` | Native shell, notebook persistence, and backup export. |
| `macos/Updates/` | Release checks, update verification, and installation. |
| `macos/Icon.swift` | App icon renderer. |
| `scripts/build-mac.py` | Universal app, disk image, and signed update builder. |
| `tests/` | Task, import, reminder, and native updater tests. |

### Test and build

Building requires Apple command-line developer tools, Python 3, and access to the existing release-signing key. JavaScript tests require Node.js.

```sh
# Test task logic, imports, and reminders.
node --test tests/*.test.mjs

# Build the universal app, DMG, and signed update assets.
python3 scripts/build-mac.py

# Build and run native updater tests.
swiftc -module-cache-path build/ModuleCache \
  macos/Updates/UpdateCore.swift \
  macos/Updates/UpdatePublicKey.swift \
  macos/Updates/InstallCore.swift \
  tests/UpdaterTests.swift \
  -o build/updater-tests
build/updater-tests
```

### Publish a release

The builder compiles both Mac architectures, bundles the interface for offline use, generates the icon, signs the app ad hoc, and verifies the disk image. Build products are ignored by Git.

Attach the following assets to each published `vX.Y.Z` release:

- The versioned universal DMG.
- `Daybook-update.zip`.
- `daybook-update.json` and `daybook-update.sig`.
- The versioned checksum file.

The updater selects the newest published, non-prerelease version.

The Ed25519 private signing key stays in macOS Keychain under service `com.avisharma.daybook.release-signing`, account `ed25519-v1`; its public key is pinned in `macos/Updates/`. Builds fail when the key is missing or mismatched. Do not regenerate it for routine releases. Losing the key requires a manual reinstall with a new trust key; `scripts/SignUpdate.swift initialize` is for initial setup only.

See [CHANGELOG.md](CHANGELOG.md) for version history.
