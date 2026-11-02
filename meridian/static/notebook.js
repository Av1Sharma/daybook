"use strict";
// Shared notebook views. All user text is escaped before entering markup.
let notebookState = {
  notes: [],
  archived_notes: [],
  history: [],
  events: [],
  cadences: [],
  trash: [],
  categories: [],
};
let noteSearch = "",
  noteArchived = false,
  taskSort = "suggested",
  notebookFilter = "all",
  calendarCourse = "all";
const smallDate = (key) =>
  key
    ? Dates.format(key.slice(0, 10), {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "No date";
function notebookTaskModal(id = null, day = null) {
  const t = id === null ? {} : state.tasks.find((t) => t.id === id);
  if (!t) return toast("This task is no longer available.");
  const categories = notebookState.categories;
  openModal(
    id === null ? "Add task" : "Edit task",
    `<form id="notebook-task-form"><label for="nt-title">Task</label><input id="nt-title" required maxlength="300" value="${esc(t.title || "")}" placeholder="What needs doing?"><label for="nt-due">Due date</label><input id="nt-due" type="date" value="${esc(t.due_date || (t.due_at ? Dates.dayKey(t.due_at,state.timezone) : null) || day || "")}"><label for="nt-notes">Notes</label><textarea id="nt-notes" maxlength="20000">${esc(t.notes || "")}</textarea><details class="task-options"><summary>More options</summary><label for="nt-time">Time (optional, ${esc(state.timezone)})</label><input id="nt-time" type="time" value="${t.due_at ? new Intl.DateTimeFormat("en-GB",{timeZone:state.timezone,hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(new Date(t.due_at)) : ""}"><button type="button" class="text-button" id="nt-clear">Clear date</button><label for="nt-course">Course or context</label><input id="nt-course" maxlength="100" value="${esc(t.course || "")}"><div class="form-row"><div><label for="nt-category">Category</label><select id="nt-category">${categories.map(c=>`<option ${c === (t.notebook_category || (t.category === "academic" ? "Academics / classes" : t.category === "career" ? "Internships / jobs" : "Personal")) ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div><div><label for="nt-importance">Importance</label><select id="nt-importance">${[[1,"Low"],[2,"Normal"],[3,"High"]].map(([v,label])=>`<option value="${v}" ${v === (t.importance || 2) ? "selected" : ""}>${label}</option>`).join("")}</select></div></div><label for="nt-repeat">Repeat</label><select id="nt-repeat">${["none","daily","weekly"].map(v=>`<option ${v === (t.repeat_rule || "none") ? "selected" : ""}>${v}</option>`).join("")}</select><label for="nt-effort">Estimated minutes (0 = unknown)</label><input id="nt-effort" type="number" min="0" max="1440" value="${t.minutes || 0}" required>${id !== null ? '<button type="button" id="nt-delete" class="text-button spaced">Move to trash</button>' : ""}</details>${t.evidence?.length ? `<details class="task-options"><summary>Source</summary>${t.evidence.map(e=>`<blockquote>${esc(e.quote)}</blockquote>${e.source_url ? `<a href="${esc(e.source_url)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>` : ""}`).join("")}</details>` : ""}<div class="error" id="form-error" role="alert"></div><div class="form-actions"><button class="button dark">${id === null ? "Add task" : "Save"}</button></div></form>`,
  );
  document
    .querySelectorAll("[data-due-shortcut]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          ($("#nt-due").value = Dates.addDays(
            Dates.dayKey(state.now, state.timezone),
            Number(b.dataset.dueShortcut),
          ))),
    );
  $("#nt-clear").onclick = () => {
    $("#nt-due").value = "";
    $("#nt-time").value = "";
  };
  $("#notebook-task-form").onsubmit = async (e) => {
    e.preventDefault();
    const b = e.submitter;
    b.disabled = true;
    try {
      await api(
        id === null ? "/api/notebook/tasks" : "/api/notebook/tasks/" + id,
        id === null ? "POST" : "PUT",
        {
          title: $("#nt-title").value,
          notebook_category: $("#nt-category").value,
          course: $("#nt-course").value,
          importance: Number($("#nt-importance").value),
          due_date: $("#nt-due").value || null,
          due_at:
            $("#nt-time").value && $("#nt-due").value
              ? Dates.atZone(
                  $("#nt-due").value,
                  $("#nt-time").value,
                  state.timezone,
                )
              : null,
          repeat_rule: $("#nt-repeat").value,
          minutes: Number($("#nt-effort").value),
          notes: $("#nt-notes").value,
          demo,
        },
      );
      modal.close();
      await refresh();
      toast("Your next step is saved.");
    } catch (err) {
      errorInForm(err);
    } finally {
      b.disabled = false;
    }
  };
  if (id !== null) {
    $("#nt-delete").onclick = async () => {
      try {
        await api("/api/notebook/tasks/" + id, "DELETE");
        modal.close();
        await refresh();
        toast("Moved to trash. Restore it using the Trash filter in All tasks.");
      } catch (e) {
        errorInForm(e);
      }
    };
    if ($("#nt-complete")) $("#nt-complete").onclick = async () => {
      try {
        await api("/api/tasks/" + id, "PATCH", { completed: !t.completed });
        modal.close();
        await refresh();
        toast(t.completed ? "Task reopened." : "One thing moved forward.");
      } catch (e) {
        errorInForm(e);
      }
    };
  }
}
function donePage() {
  const groups = new Map();
  for (const e of notebookState.history) {
    const day = e.date_only
      ? e.completed_at.slice(0, 10)
      : Dates.dayKey(e.completed_at, state.timezone);
    if (!groups.has(day)) groups.set(day, []);
    groups.get(day).push(e);
  }
  return (
    head(
      "The things you moved forward.",
      "Your Daybook history, and everything you complete from here.",
      "DAY DONE",
    ) +
      `<div class="history-summary"><strong>${notebookState.history.length}</strong><span>recorded completions · small steps count, too</span></div>` +
      [...groups.entries()]
        .sort((a, b) => b[0].localeCompare(a[0]))
        .map(
          ([day, events]) =>
            `<section class="panel history-group"><div class="section-title"><h2>${Dates.format(day, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</h2><span class="tag">${events.length} completed</span></div>${events.map((e) => `<div class="completion-row"><span class="completion-check">${icon("check")}</span><div><b>${esc(e.title)}</b><small>${e.date_only ? "Date recorded · time unknown" : time(e.completed_at)} · ${e.kind === "reminder" ? "Reminder check-in" : "Task"}${e.minutes ? " · " + e.minutes + " min estimated" : ""}</small></div><button class="text-button" data-reopen-kind="${e.kind}" data-reopen-id="${e.id}">Reopen</button></div>`).join("")}</section>`,
        )
        .join("") ||
    '<div class="empty">Your first completion will appear here.</div>'
  );
}
function notesPage() {
  const notes = (
    noteArchived ? notebookState.archived_notes : notebookState.notes
  ).filter((n) =>
    (n.title + " " + n.description + " " + JSON.stringify(n.items))
      .toLowerCase()
      .includes(noteSearch.toLowerCase()),
  );
  return (
    head(
      "A place for what you want to keep.",
      "Reference collections, company lists, and notes from Daybook.",
      "REFERENCE NOTES",
    ) +
    `<div class="toolbar"><input type="search" id="note-search" aria-label="Search reference notes" placeholder="Find a note or company…" value="${esc(noteSearch)}"><button class="button" id="notes-archived">${noteArchived ? "Show current notes" : "Show archived"}</button><button class="button dark" id="new-note">${icon("plus")}New note</button></div><div class="notes-grid">${
      notes
        .map(
          (n) =>
            `<article class="panel note-card"><span class="tag">${n.scope === "internships" ? "Internships / jobs" : "Reference"}</span><h2>${esc(n.title)}</h2><p class="note-description">${esc(n.description)}</p><ul>${n.items
              .slice(0, 8)
              .map(
                (item) =>
                  `<li>${esc(typeof item === "string" ? item : JSON.stringify(item))}</li>`,
              )
              .join(
                "",
              )}</ul>${n.items.length > 8 ? `<p class="help">+${n.items.length - 8} more items</p>` : ""}<button class="text-button" data-note="${n.id}">Open & edit ${icon("arrow")}</button></article>`,
        )
        .join("") ||
      '<div class="empty">Keep a useful list or a thought for later.</div>'
    }</div>`
  );
}
function noteModal(id = null) {
  const n =
    [...notebookState.notes, ...notebookState.archived_notes].find(
      (n) => n.id === id,
    ) || {};
  openModal(
    id === null ? "Keep something useful." : n.title,
    `<form id="note-form"><label for="note-title">Title</label><input id="note-title" required maxlength="300" value="${esc(n.title || "")}"><label for="note-description">Notes</label><textarea id="note-description" maxlength="20000">${esc(n.description || "")}</textarea><label for="note-items">List (one item per line)</label><textarea id="note-items" rows="10">${esc((n.items || []).map((i) => (typeof i === "string" ? i : JSON.stringify(i))).join("\n"))}</textarea><label for="note-scope">Collection</label><select id="note-scope"><option value="general">General reference</option><option value="internships" ${n.scope === "internships" ? "selected" : ""}>Internships / jobs</option></select><div class="error" id="form-error" role="alert"></div><div class="form-actions">${id !== null ? `<button type="button" id="archive-note" class="button">${n.archived ? "Restore" : "Archive"}</button>` : ""}<button class="button dark">Save note</button></div></form>`,
  );
  const save = async (archived) => {
    try {
      let items = $("#note-items")
        .value.split("\n")
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => {
          try {
            const v = JSON.parse(s);
            return typeof v === "object" && v !== null ? v : s;
          } catch {
            return s;
          }
        });
      await api(
        id === null ? "/api/reference-notes" : "/api/reference-notes/" + id,
        id === null ? "POST" : "PUT",
        {
          title: $("#note-title").value,
          description: $("#note-description").value,
          items,
          scope: $("#note-scope").value,
          archived,
          demo,
        },
      );
      modal.close();
      await refresh();
      toast("Note saved.");
    } catch (e) {
      errorInForm(e);
    }
  };
  $("#note-form").onsubmit = (e) => {
    e.preventDefault();
    save(!!n.archived);
  };
  if ($("#archive-note")) $("#archive-note").onclick = () => save(!n.archived);
}
function notebookPage() {
  return (
    head(
      "Your notebook, safely together.",
      "Daybook and Daybook share one home. Keep a backup whenever you need one.",
      "NOTEBOOK & BACKUPS",
    ) +
    `<div class="notes-grid"><section class="panel"><h2>A copy to keep.</h2><p>Export tasks, evidence, notes, calendar events, reminders, and history. Credentials stay in Keychain.</p><a class="button dark" href="/api/backup" download>Export notebook</a><button class="button" id="restore-backup">Restore backup…</button><p class="help">Restoring replaces this notebook. Daybook creates a safety backup first.</p></section><section class="panel"><h2>Bring Daybook along.</h2><p>Merge a Daybook notebook or backup. Existing Daybook records stay in place. Re-imports preserve edits and skip duplicates.</p><button class="button" id="import-daybook">Merge Daybook…</button><p class="help">The original Daybook file remains intact. Mac app: Workspace → Show Data Folder → Backups.</p></section></div><section class="panel history-group"><h2>Trash</h2><p class="help">Tasks stay recoverable until you restore a different backup.</p>${notebookState.trash.map((t) => `<div class="completion-row"><div><b>${esc(t.title)}</b><small>${smallDate(t.deleted_at)}</small></div><button class="text-button" data-restore-task="${t.id}">Restore</button></div>`).join("") || '<div class="empty">Nothing in the trash.</div>'}</section><p class="help">On Mac, Workspace also has the floating task window (⇧⌘T) and optional reminder settings. Daybook must stay running for desktop reminders.</p>`
  );
}
function fileModal(restore) {
  openModal(
    restore ? "Restore your notebook." : "Bring Daybook into Daybook.",
    `<p class="help">${restore ? "This replaces the current notebook. A safety backup is saved automatically. Gmail credentials are unaffected." : "Choose Daybook’s notebook.json or an exported backup. Your current Daybook records are preserved."}</p><form id="backup-form"><label for="backup-file">Notebook JSON file</label><input type="file" id="backup-file" accept=".json,application/json" required>${restore ? '<label class="check-label"><input type="checkbox" id="restore-confirm" required>I understand this replaces the current notebook.</label>' : ""}<div class="error" id="form-error" role="alert"></div><div class="form-actions"><button class="button dark">${restore ? "Restore notebook" : "Merge Daybook"}</button></div></form>`,
  );
  $("#backup-form").onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      const file = $("#backup-file").files[0];
      if (file.size > 50000000)
        throw Error("Choose a notebook smaller than 50 MB.");
      const r = await api(
        restore ? "/api/backup/restore" : "/api/daybook/import",
        "POST",
        JSON.parse(await file.text()),
      );
      modal.close();
      demo = false;
      localStorage.setItem("meridian-demo", "false");
      await refresh();
      toast(
        restore
          ? "Notebook restored. Safety backup saved."
          : r.already_imported
            ? "This Daybook notebook is already merged."
            : `Merged ${r.tasks} tasks, ${r.notes} notes, and ${r.events} events.`,
      );
    } catch (err) {
      errorInForm(err);
      e.submitter.disabled = false;
    }
  };
}
function calendarEventsOn(day) {
  const events = notebookState.events.filter(
    (e) =>
      e.date <= day &&
      (e.end_date || e.date) >= day &&
      (calendarCourse === "all" ||
        e.course === calendarCourse ||
        e.kind === "break"),
  );
  const sunday = new Date(day + "T12:00:00Z").getUTCDay();
  for (const c of notebookState.cadences) {
    if (
      c.enabled === false ||
      !c.weekdays?.includes(sunday) ||
      day < (c.start || "0000") ||
      day > (c.end || "9999") ||
      events.some((e) => e.kind === "break") ||
      (calendarCourse !== "all" && c.course !== calendarCourse)
    )
      continue;
    events.push({
      id: "cadence:" + c.id,
      title: c.title || "Cadence reminder",
      course: c.course,
      date: day,
      kind: "cadence",
      notes:
        "Cadence only. Confirm the actual assignment and submission time in your course system.",
    });
  }
  return events;
}
function eventCards(day) {
  return calendarEventsOn(day)
    .map(
      (e) =>
        `<button class="agenda-block event-card ${e.tentative ? "tentative" : ""}" data-event="${esc(e.id)}"><span>${e.time || "All day"}${e.end_time ? " – " + esc(e.end_time) : ""} · ${esc(e.course || e.kind)}</span><b>${esc(e.title)}</b><small>${e.tentative ? "Tentative · " : ""}${e.linked_task_id ? (state.tasks.find((t) => t.id === e.linked_task_id)?.completed ? "Completed · " : "Tracked task · ") : ""}${esc(e.location || e.kind)}</small></button>`,
    )
    .join("");
}
function eventModal(id = null, day = null) {
  if (String(id).startsWith("cadence:")) {
    const e = calendarEventsOn(selectedDay).find((e) => String(e.id) === id);
    openModal(
      e.title,
      `<p>${esc(e.course)}</p><p class="help">${esc(e.notes)}</p>`,
    );
    return;
  }
  const e = notebookState.events.find((e) => e.id === Number(id)) || {};
  openModal(
    id === null ? "Add to your calendar." : e.title,
    `<form id="event-form"><label for="ev-title">Event title</label><input id="ev-title" required maxlength="300" value="${esc(e.title || "")}"><label for="ev-course">Course or context</label><input id="ev-course" maxlength="100" value="${esc(e.course || "")}"><div class="form-row"><div><label for="ev-date">Date</label><input type="date" id="ev-date" required value="${esc(e.date || day || selectedDay)}"></div><div><label for="ev-end">Through (optional)</label><input type="date" id="ev-end" value="${esc(e.end_date || "")}"></div></div><div class="form-row"><div><label for="ev-time">Time (optional)</label><input type="time" id="ev-time" value="${esc(e.time || "")}"></div><div><label for="ev-end-time">End time (optional)</label><input type="time" id="ev-end-time" value="${esc(e.end_time || "")}"></div></div><div class="form-row"><div><label for="ev-kind">Type</label><select id="ev-kind">${["deadline", "exam", "activity", "break", "reference"].map((v) => `<option ${e.kind === v ? "selected" : ""}>${v}</option>`).join("")}</select></div><div><label for="ev-location">Location</label><input id="ev-location" maxlength="500" value="${esc(e.location || "")}"></div></div><label class="check-label"><input id="ev-tentative" type="checkbox" ${e.tentative ? "checked" : ""}>Tentative · needs confirmation</label><label for="ev-notes">Notes</label><textarea id="ev-notes" maxlength="20000">${esc(e.notes || "")}</textarea><label for="ev-source">Source or reference</label><input id="ev-source" maxlength="2000" value="${esc(e.source || "")}">${e.linked_task_id ? '<p class="note">This event has a tracked task. Edit its deadline separately if the date changes.</p>' : ""}<p class="help">A date without a time stays all day. Breaks and tentative events stay as calendar references.</p><div class="error" id="form-error" role="alert"></div><div class="form-actions">${id !== null ? '<button type="button" class="text-button" id="ev-remove">Remove event</button><button type="button" class="button" id="ev-track">' + (e.linked_task_id ? "Open tracked task" : "Track as task") + "</button>" : ""}<button class="button dark">Save event</button></div></form>`,
  );
  $("#event-form").onsubmit = async (event) => {
    event.preventDefault();
    try {
      await api(
        id === null ? "/api/calendar-events" : "/api/calendar-events/" + id,
        id === null ? "POST" : "PUT",
        {
          title: $("#ev-title").value,
          course: $("#ev-course").value,
          date: $("#ev-date").value,
          end_date: $("#ev-end").value || null,
          time: $("#ev-time").value || null,
          end_time: $("#ev-end-time").value || null,
          kind: $("#ev-kind").value,
          location: $("#ev-location").value,
          tentative: $("#ev-tentative").checked,
          notes: $("#ev-notes").value,
          source: $("#ev-source").value,
          demo,
        },
      );
      modal.close();
      await refresh();
      toast("Calendar event saved.");
    } catch (err) {
      errorInForm(err);
    }
  };
  if ($("#ev-remove"))
    $("#ev-remove").onclick = async () => {
      try {
        await api("/api/calendar-events/" + id, "DELETE");
        modal.close();
        await refresh();
      } catch (err) {
        errorInForm(err);
      }
    };
  if ($("#ev-track"))
    $("#ev-track").onclick = async () => {
      try {
        const r = await api("/api/calendar-events/" + id + "/track", "POST");
        modal.close();
        await refresh();
        evidence(r.id);
      } catch (err) {
        errorInForm(err);
      }
    };
}
function weeklyBacklog(r) {
  return `<section class="panel history-group"><h2>The shape of your week.</h2><p class="help">Reviewed tasks with known creation dates only. ${r.review_count || 0} items awaiting review stay outside your workload. ${r.unknown_created || 0} imported records have an unknown creation date and stay outside this table. Future days are blank.</p><div class="table-scroll"><table class="backlog-table"><thead><tr><th>Day</th><th>Added</th><th>Done</th><th>Open at day’s end</th></tr></thead><tbody>${r.days.map((d) => `<tr><th>${smallDate(d.date)}${d.today ? " · so far" : ""}</th><td>${d.future ? "—" : d.added}</td><td>${d.future ? "—" : d.count}</td><td>${d.future ? "—" : d.open}</td></tr>`).join("")}</tbody></table></div></section>`;
}
function syncProgressMarkup(p) {
  if (!p?.accounts?.length) return "";
  return `<div class="sync-progress" role="status"><b>${p.running ? "Checking dated interview emails…" : p.sync?.status === "ok" ? "Interview email scan complete" : "Saved Gmail progress"}</b><p>${esc(p.sync?.detail?.startsWith("{") ? "Message checkpoints are saved on this Mac." : p.sync?.detail || "")}</p>${p.accounts.map((a) => `<div><span>${esc(a.account)}</span><strong>${a.saved_messages} messages saved · ${esc(a.state)}</strong></div>`).join("")}<small>Last 30 days · Interview emails with explicit dates only. Unrelated and undated messages are skipped.</small></div>`;
}
function bindNotebook() {
  for (const [selector, handler] of [
    ["#new-note", () => noteModal()],
    [
      "#notes-archived",
      () => {
        noteArchived = !noteArchived;
        render();
      },
    ],
    ["#import-daybook", () => fileModal(false)],
    ["#restore-backup", () => fileModal(true)],
    ["#new-event", () => eventModal(null, selectedDay)],
    ["#new-cadence", () => cadenceModal()],
  ])
    if ($(selector)) $(selector).onclick = handler;
  if ($("#note-search"))
    $("#note-search").oninput = (e) => {
      noteSearch = e.target.value;
      const pos = e.target.selectionStart;
      render();
      $("#note-search").focus();
      $("#note-search").setSelectionRange(pos, pos);
    };
  document
    .querySelectorAll("[data-note]")
    .forEach((b) => (b.onclick = () => noteModal(Number(b.dataset.note))));
  document
    .querySelectorAll("[data-event]")
    .forEach((b) => (b.onclick = () => eventModal(b.dataset.event)));
  document.querySelectorAll("[data-restore-task]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api(
            "/api/notebook/tasks/" + b.dataset.restoreTask + "/restore",
            "POST",
          );
          await refresh();
          toast("Task restored.");
        } catch (e) {
          toast(e.message);
        }
      }),
  );
  document.querySelectorAll("[data-reopen-id]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api("/api/activity/" + b.dataset.reopenId + "/reopen", "POST");
          await refresh();
          toast("Reopened. Completion history updated.");
        } catch (e) {
          toast(e.message);
        }
      }),
  );
  for (const [selector, key] of [
    ["#notebook-filter", "category"],
    ["#task-sort", "sort"],
    ["#calendar-course", "course"],
  ])
    if ($(selector))
      $(selector).onchange = (e) => {
        if (key === "category") notebookFilter = e.target.value;
        else if (key === "sort") taskSort = e.target.value;
        else calendarCourse = e.target.value;
        render();
      };
}
function cadenceModal() {
  openModal(
    "A familiar course rhythm.",
    `${notebookState.cadences.length ? `<section class="panel"><h3>Saved cadences</h3>${notebookState.cadences.map((c) => `<div class="completion-row"><div>${esc(c.course)} · ${esc(c.title)}</div><button class="text-button" type="button" data-remove-cadence="${esc(c.id)}">Remove</button></div>`).join("")}</section>` : ""}<form id="cadence-form"><label for="cad-title">Reminder</label><input id="cad-title" maxlength="300" required placeholder="Check for weekly homework"><label for="cad-course">Course</label><input id="cad-course" maxlength="100" required><label for="cad-start">From</label><input id="cad-start" type="date" required value="${selectedDay}"><label for="cad-end">Through</label><input id="cad-end" type="date" required><fieldset><legend>Days</legend><div class="cadence-days">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d, i) => `<label><input type="checkbox" name="weekday" value="${i}">${d}</label>`).join("")}</div></fieldset><p class="help">Cadences are reminders, not deadlines. Breaks are skipped automatically.</p><div class="error" id="form-error" role="alert"></div><div class="form-actions"><button class="button dark">Save cadence</button></div></form>`,
  );
  document.querySelectorAll("[data-remove-cadence]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api(
            "/api/calendar-cadences/" +
              encodeURIComponent(b.dataset.removeCadence),
            "DELETE",
          );
          modal.close();
          await refresh();
          toast("Cadence removed.");
        } catch (e) {
          errorInForm(e);
        }
      }),
  );
  $("#cadence-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/calendar-cadences", "POST", {
        title: $("#cad-title").value,
        course: $("#cad-course").value,
        start: $("#cad-start").value,
        end: $("#cad-end").value,
        weekdays: [
          ...document.querySelectorAll('[name="weekday"]:checked'),
        ].map((i) => Number(i.value)),
        demo,
      });
      modal.close();
      await refresh();
      toast("Course cadence saved.");
    } catch (err) {
      errorInForm(err);
    }
  };
}
