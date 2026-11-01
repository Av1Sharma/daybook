# Daybook

A local Mac task notebook: Today, All tasks, Calendar, Day done, and Week done. This is the continuation of Daybook, incorporating the local Python service and Gmail integration previously developed as Meridian.

## What changed in 2.0

- Today shows tasks due today or overdue, with no scheduling dashboard.
- All tasks has search and one status filter (Open, Completed, Trash).
- Week done is a simple weekly completion history.
- Syllabus imports preview dates before saving. Choose Calendar only, Task + calendar, or Skip. Past dates default to Calendar only; uncertain dates stay unsaved until corrected.
- PDF/text import runs locally. Date-only deadlines remain date-only; unknown times and TBA dates are never invented.
- Repeated imports do not duplicate records or reopen completed tasks.
- The existing Calendar and Day done views remain available. Connections holds import and Gmail setup.

## Run from source

Requires Python 3.11+ and Node.js for JavaScript checks.

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m uvicorn meridian.app:app --host 127.0.0.1 --port 18765
```

Open `http://127.0.0.1:18765`. The internal Python package, environment variables, local port, bundle identifier and Keychain service retain their `meridian` names for compatibility. They do not identify a separate app.

## Mac app

```sh
.venv/bin/python scripts/build-mac.py
```

The build creates `../Daybook.app`, with a bundled virtual environment, native task window, and verified signed-update support. The local build uses the installed Python framework; it is not a portable or notarized distribution.

Existing Meridian installations continue using `~/Library/Application Support/Meridian`, including the SQLite notebook, connection metadata, backups and preferences. Credentials remain in the same macOS Keychain service. Original Daybook JSON notebooks can be merged with the existing validated notebook migration API; the originals remain untouched. Renaming the app does not move, overwrite or silently merge another notebook.

## Imports and privacy

Use Connections → Import syllabus, supply a course and year, then choose a PDF or paste dated assignment lines. Review every extracted row before saving. Complex PDF tables may need corrected dates in the preview; a date is required for every selected row. Importing old coursework does not claim that it was completed.

Gmail is optional and read-only. Only interview emails with clear dates become tasks. Google OAuth credentials are configured locally, not bundled or stored in this repository. Database contents are plaintext on the local filesystem; credentials are excluded from notebook exports. Local write requests require an in-memory token and same-origin validation.

Personal syllabi, screenshots, notebooks, databases, account settings, credentials, and built app bundles are not included in the source repository.

## Validation

```sh
.venv/bin/python -m pytest -q
node --check meridian/static/app.js
node --check meridian/static/notebook.js
node --test tests/calendar.test.cjs
```

CI also compiles the Mac app and runs desktop and updater security tests. Signed update metadata must use the pinned verification key; older Daybook 1.x update signatures are not accepted by the 2.x updater. Updates are sourced exclusively from `Av1Sharma/daybook`. The former frontend is retained in this repository’s Git history.
