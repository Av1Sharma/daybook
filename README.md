# Daybook

A personal, single-user task notebook based on the supplied Notes workflow. No package installation or build step is required.

## Use

On this Mac, double-click `Start Daybook.command` to start and open the app. Keep its window open while using Daybook. Python 3 is required (available on the development machine).

Serve `dist` with a local HTTP server, for example `python3 -m http.server 4173 --directory dist`, then open http://localhost:4173. Use the same address and browser for everyday use so the notebook stays consistent.

- Enter tasks at the top. Newest-first is the default; Suggested and Due date ordering are optional.
- Add details for category, a due date (Today/Tomorrow/In a week shortcuts), quiet importance, recurrence, and an effort estimate.
- Check off a task to move it to dated DAY DONE history. Undo or click its check in history to reopen it.
- Everyday and weekly recurrence create one future occurrence, measured from the actual completion day. Missed days do not create a pile of duplicate tasks. Future occurrences cannot be completed before their scheduled day. Editing the date changes the schedule.
- Weekly review includes daily completions, category totals, unfinished/overdue work, estimated completed effort, and end-of-day backlog. Today is partial. Future days have no backlog value. Future repeat occurrences are excluded from current unfinished counts.
- Observations describe recorded activity rather than assuming quiet days mean poor productivity. Effort is estimated, not tracked time.

## Storage

Task data is saved in this browser's localStorage, under `daybook.notebook.v1`. There is no server task database, cross-device sync, or external integration. Different browser profiles and origins have separate notebooks. Clearing site data removes the notebook. “Back up notebook” downloads its JSON. The MVP exports backups; it does not yet have an in-app restore screen.

The app starts empty. Screenshot tasks/history were design context and have not been silently imported. Categories reflect classes, coding, applications, projects, and personal tasks. Sample records used for testing exist only in the local test browser, not the site source.

## Verification

Run `node --test tests/model.test.mjs` for date boundaries, validation, completion/reopen, recurrence, recommendations, and weekly calculations. Main browser flows were checked at desktop and 375px width: create with details, reload persistence, completion, undo, edit, recurrence, weekly review, overdue labels, and newest-first order. The two optional WebMCP tools were exercised for valid input, invalid input, and read-back.

## Files

- `dist/index.html`: accessible document and forms.
- `dist/style.css`: responsive Notes-inspired presentation.
- `dist/model.mjs`: date helpers and task transitions.
- `dist/app.js`: rendering, interaction, local persistence, and optional WebMCP registration.
- `tests/model.test.mjs`: core regression tests.

Weekly backlog is reconstructed from created/completed/deleted dates. Editing an old task's schedule or reopening it can revise historical unfinished counts; this MVP is not an immutable event ledger.

## Publishing status

A private Site was registered, but no version was published: the installed Sites publishing helper became unavailable during this session. The local application is complete and does not depend on that service.
