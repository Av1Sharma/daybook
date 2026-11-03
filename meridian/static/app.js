"use strict";
const $ = (s) => document.querySelector(s);
const icons = {
  edit: '<path d="m15 4 5 5M4 20l5-1L21 7a3.5 3.5 0 0 0-5-5L4 15z"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  chart: '<path d="M4 3v18h17M8 16v-4m5 4V8m5 8V5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4L19 5"/>',
  check:
    '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="m8 12 3 3 5-6"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-12 4h2m3 0h2"/>',
  book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1zm0 0v15"/>',
  inbox: '<path d="m5 4-3 10v6h20v-6L19 4zm-3 10h6l2 3h4l2-3h6"/>',
  shield:
    '<path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6z"/><path d="m8 12 3 3 5-6"/>',
  refresh:
    '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.2 6a8 8 0 0 1 13 1L20 12M4 12l.8 5a8 8 0 0 0 13 1"/>',
  plus: '<path d="M12 4v16M4 12h16"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  spark:
    '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  flag: '<path d="M5 22V3m0 1c6-5 8 5 14 0v10c-6 5-8-5-14 0"/>',
  leaf: '<path d="M20 3c-1 10-2 17-10 17-8 0-8-9-3-12 4-3 8-1 13-5zM4 22 16 10"/>',
  link: '<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 2 1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>',
};
const icon = (n) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[n] || icons.check}</svg>`;
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const availableViews = new Set([
  "today",
  "done",
  "tasks",
  "calendar",
  "weekly",
  "sources",
]);
let taskLimit = 60;
let state,
  view = availableViews.has(location.hash.slice(1))
    ? location.hash.slice(1)
    : "today",
  filter = "all",
  query = "",
  calendarMonth = null,
  selectedDay = null,
  reviewWeek = null,
  reviewData = null,
  reminderFilter = "ready",
  reminderSearch = "",
  reviewRequest = 0,
  demo = false;
const Dates = MeridianDates;
const modal = $("#modal");
const date = (d, opts = {}) =>
  new Intl.DateTimeFormat("en-US", {
    timeZone: state?.timezone || "America/New_York",
    ...opts,
  }).format(new Date(d));
const localDay = (d) =>
  date(d, { year: "numeric", month: "2-digit", day: "2-digit" });
const time = (d) => date(d, { hour: "numeric", minute: "2-digit" });
const dayLabel = (d) => date(d, { month: "short", day: "numeric" });
const active = () =>
  state.tasks.filter(
    (t) =>
      !t.completed &&
      t.confidence !== "review" &&
      (!t.available_on ||
        t.available_on <= Dates.dayKey(state.now, state.timezone)),
  );
function toast(text) {
  $("#toast").textContent = text;
  $("#toast").style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").style.display = "none"), 5500);
}
async function api(path, method = "GET", body) {
  const r = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(state ? { "X-Meridian-Token": state.token } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!r.ok) {
    let d;
    try {
      d = await r.json();
    } catch {
      throw Error(
        `Request failed (${r.status}). Reload the page and try again.`,
      );
    }
    throw Error(
      typeof d.detail === "string"
        ? d.detail
        : "Please check the form values and timezone.",
    );
  }
  return r.json();
}
async function refresh() {
  canLeaveReflection();
  if (view === "weekly") reviewData = null;
  try {
    const results = await Promise.all([
      api("/api/state?demo=" + demo),
      api("/api/notebook?demo=" + demo),
      api("/api/sync/progress"),
    ]);
    state = results[0];
    notebookState = results[1];
    state.syncProgress = results[2];
    render();
    const focusTask = new URLSearchParams(location.search).get("task");
    if (focusTask && state.tasks.some((t) => t.id === Number(focusTask))) {
      history.replaceState(null, "", location.pathname + location.hash);
      evidence(Number(focusTask));
    }
  } catch (e) {
    $("#view").innerHTML =
      `<div class="error-page"><h1>Let’s reconnect.</h1><p>${esc(e.message)}</p><button class="button" id="retry">Try again</button></div>`;
    $("#retry").onclick = refresh;
  }
}
function head(title, subtitle, eyebrow = "YOUR WORKSPACE") {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="subtitle">${subtitle}</p></div><div class="date-chip">${icon("calendar")}${date(state.now, { weekday: "short", month: "short", day: "numeric" })}</div></div>`;
}
function confidence(t) {
  return `<span class="tag ${t.confidence}">${{ confirmed: "Confirmed", expected: "Expected", review: "Needs review" }[t.confidence]}</span>`;
}
function due(t) {
  if (!t.due_at)
    return t.due_date
      ? `<span>${t.due_date < Dates.dayKey(state.now, state.timezone) ? "Overdue · " : ""}${smallDate(t.due_date)}</span><small>Date only</small>`
      : `<span>${t.notebook_id ? "Whenever you’re ready" : "Date unconfirmed"}</span>`;
  const hours = (new Date(t.due_at) - new Date(state.now)) / 36e5;
  return `<${hours < 48 ? "strong" : "span"}>${hours < 0 ? "Overdue · " : ""}${localDay(t.due_at) === localDay(state.now) ? "Today" : dayLabel(t.due_at)}</${hours < 48 ? "strong" : "span"}><small>${time(t.due_at)}</small>`;
}
function taskRow(t) {
  return `<div class="task-row ${t.completed ? "done" : ""}"><input type="checkbox" class="task-check" data-complete="${t.id}" ${t.completed ? "checked" : ""} aria-label="Mark ${esc(t.title)} ${t.completed ? "incomplete" : "complete"}"><div class="task-main"><button class="task-title" data-task="${t.id}">${esc(t.title)}</button><div class="task-meta"><span class="tag ${t.category}">${esc(t.course)}</span><span>${t.minutes ? t.minutes + " min" : ""}</span>${t.repeat_rule && t.repeat_rule !== "none" ? `<span>· ${esc(t.repeat_rule)}</span>` : ""}${t.available_on && t.available_on > Dates.dayKey(state.now, state.timezone) ? `<span>Available ${smallDate(t.available_on)}</span>` : ""}${t.confidence !== "confirmed" ? confidence(t) : ""}</div></div><div class="task-due">${due(t)}</div></div>`;
}
function taskList(tasks) {
  return `<div class="task-list">${tasks.length ? tasks.map(taskRow).join("") : '<div class="empty"><h3>A little breathing room.</h3>No tasks here. Import a syllabus, connect your sources, or add your next step.</div>'}</div>`;
}
function stats() {
  return `<div class="stats">${[
    [
      "Open tasks",
      state.briefing.open,
      "Across academics & career",
      "check",
      "",
    ],
    [
      "Due in 48 hours",
      state.briefing.due_soon,
      "Your nearest deadlines",
      "flag",
      "",
    ],
    [
      "Planned effort",
      (state.briefing.minutes / 60).toFixed(1) + '<span class="unit"> h</span>',
      "Estimated remaining work",
      "clock",
      "",
    ],
    [
      "Course date checks",
      state.briefing.review,
      "A little context goes a long way",
      "inbox",
      "accent",
    ],
  ]
    .map(
      ([label, n, sub, i, c]) =>
        `<div class="stat"><div class="stat-top">${label}<span class="stat-icon">${icon(i)}</span></div><strong class="${c}">${n}</strong><small>${sub}</small></div>`,
    )
    .join("")}</div>`;
}
function today() {
  const key = Dates.dayKey(state.now, state.timezone);
  const tasks = active().filter(t => {
    const day = t.due_date || (t.due_at ? Dates.dayKey(t.due_at, state.timezone) : null);
    return day && day <= key;
  });
  return `<div class="today-heading"><div><p class="eyebrow">${date(state.now, {weekday:"long", month:"long", day:"numeric"})}</p><h1>Today</h1><p class="subtitle">${tasks.length ? tasks.length + " tasks due today or overdue" : "Nothing due today."}</p></div></div><section class="simple-tasks" aria-label="Today’s tasks">${tasks.length ? taskList(tasks) : '<div class="empty">You’re clear for today. Your upcoming work is in All tasks.</div>'}</section><button class="text-button spaced" data-view="tasks">All tasks ${icon("arrow")}</button>`;
}
function tasksPage() {
  if (filter === "trash") {
    const items = notebookState.trash.filter(t => t.title.toLowerCase().includes(query.toLowerCase()));
    return head("All tasks", "") + taskTools() + `<div class="task-list">${items.map(t => `<div class="task-row"><div class="task-main">${esc(t.title)}</div><button class="text-button" data-restore-task="${t.id}">Restore</button></div>`).join("") || '<div class="empty">Trash is empty.</div>'}</div>`;
  }
  const tasks = state.tasks.filter(t => t.confidence !== "review" && (filter === "completed" ? t.completed : !t.completed) && (t.title + " " + t.course).toLowerCase().includes(query.toLowerCase()));
  tasks.sort((a,b) => (a.due_date || a.due_at || "9999").localeCompare(b.due_date || b.due_at || "9999"));
  return head("All tasks", "") + taskTools() + taskList(tasks.slice(0,taskLimit)) + (tasks.length > taskLimit ? `<button class="button spaced" id="more-tasks">Show more</button>` : "");
}
function taskTools() {
  return `<div class="toolbar simple-toolbar"><input id="search" type="search" aria-label="Search tasks" placeholder="Search tasks…" value="${esc(query)}"><select id="task-filter" aria-label="Task status">${[["all","Open"],["completed","Completed"],["trash","Trash"]].map(([k,v]) => `<option value="${k}" ${filter === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>`;
}
function coursesPage() {
  const courses = [
    ...new Set(
      state.tasks.filter((t) => t.category === "academic").map((t) => t.course),
    ),
  ];
  return (
    head(
      "The semester, in perspective.",
      "A source-backed overview of your academic commitments.",
      "MY COURSES",
    ) +
    `<div class="course-grid">${
      courses
        .map((c) => {
          const tasks = state.tasks.filter((t) => t.course === c),
            complete = tasks.filter((t) => t.completed).length;
          return `<section class="course-card"><span class="tag">${tasks.length} obligations</span><h3>${esc(c)}</h3><p>${tasks.length - complete} open · ${tasks.filter((t) => t.confidence === "review" && !t.completed).length} need review<br>${[...new Set(tasks.map((t) => t.destination))].map(esc).join(" · ")}</p><button class="text-button" data-course="${esc(c)}">View course tasks ${icon("arrow")}</button><progress class="course-progress" value="${complete}" max="${tasks.length}" aria-label="${esc(c)} completion"></progress></section>`;
        })
        .join("") ||
      '<div class="empty">Import your first syllabus to see the semester take shape.</div>'
    }</div><div class="note">Syllabi fill the gaps: recurring homework, quizzes, and work submitted on Gradescope can appear here even when they aren’t Canvas assignments.</div>`
  );
}
function sourcesPage() {
  const status = state.connection_status;
  const last = (name) => state.syncs.find((s) => s.source === name);
  const result = (name) =>
    last(name)
      ? `<p class="help">Last sync: ${date(last(name).synced_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}<br>${last(name).status === "ok" ? "Import completed." : esc(last(name).detail)}</p>`
      : "";
  const outcome = new URLSearchParams(location.search).get("connection");
  const message = {
    connected: "Gmail is connected. Sync sources to build your plan.",
    declined:
      "Google sign-in was cancelled. Your existing connection was preserved.",
    failed:
      "Google sign-in did not finish. Check your OAuth app setup and try again.",
  }[outcome];
  return (
    head(
      "Connections",
      "Import course dates or connect Gmail.",
      "CONNECTIONS",
    ) +
    `${message ? `<p class="note" role="status">${message}</p>` : ""}<div class="connection-grid"><section class="panel connection"><span class="source-logo canvas">C</span><h2>Canvas</h2><span class="tag ${status.canvas ? "confirmed" : "review"}">${status.canvas ? "Configured" : "Manual import"}</span><p>Bring your syllabi, assignment instructions, and announcements into Daybook. No Canvas API access is needed.</p><p>Paste course text to extract obligations. When an announcement changes a date, open the task or its calendar entry, edit the deadline, and save. Original evidence stays attached.</p><div class="connection-actions"><button class="button dark" id="import-course-materials">Import course materials</button><a class="button" href="https://canvas.cornell.edu/" target="_blank" rel="noopener noreferrer">Open Canvas ↗</a></div><details class="help"><summary>Approved API connection (optional)</summary><p>Only use an institution-approved token if you have permission for this integration.</p><button class="button" id="setup-canvas">${status.canvas ? "Update Canvas setup" : "Set up approved access"}</button></details>${status.canvas ? result("canvas") : ""}${status.canvas ? '<button class="text-button" data-disconnect="canvas">Disconnect Canvas</button>' : ""}</section><section class="panel connection"><span class="source-logo gmail">M</span><h2>Gmail</h2><span class="tag ${status.gmail ? "confirmed" : "review"}">${status.gmail ? "Connected" : status.google_client ? "Ready to authorize" : "Setup needed"}</span><p>${status.google_email ? esc(status.google_email) : "Interview emails with a clear due date."}</p><p>Only interview emails with a clear deadline become tasks. Unrelated and undated emails are skipped. Connect each Gmail account in turn. Google sign-in grants read-only Gmail access. Daybook cannot send, delete, or mark messages read.</p><div class="connection-actions"><button class="button dark" id="connect-google">${status.gmail ? "Add another Gmail account" : "Connect Gmail"}</button><button class="button" id="setup-google">OAuth app setup</button></div>${result("gmail")}${syncProgressMarkup(state.syncProgress)}${status.gmail ? '<button class="text-button" data-disconnect="gmail">Disconnect Gmail</button>' : ""}</section></div><div class="note">${icon("shield")} Credentials are stored in <b>${esc(status.storage)}</b>. Your database stays on this Mac. Optional AI extraction is <b>${state.connections.ai ? "enabled: source text is sent to OpenAI" : "off: extraction stays local"}</b>.</div><div class="connection-actions spaced"><button class="button" id="refresh-connections">Refresh connection status</button><button class="button" id="import">Import a syllabus or message</button></div>`
  );
}
function connectionModal(provider) {
  const status = state.connection_status;
  const canvas = provider === "canvas";
  openModal(
    canvas ? "Connect an approved Canvas account." : "Set up Google sign-in.",
    `<form id="connection-form">${canvas ? `<p class="help">Use an institution-approved token. It is saved locally and used only by Daybook's read-only adapter.</p><label for="canvas-url">Canvas site</label><input id="canvas-url" type="url" required value="${esc(status.canvas_url)}"><label for="canvas-token">Approved access token</label><input id="canvas-token" type="password" autocomplete="off" placeholder="${status.canvas ? "Leave blank to keep the saved token" : "Paste approved token"}" ${status.canvas ? "" : "required"}>` : `<p class="help">In your Google Cloud project, enable the Gmail API and create a <b>Desktop app</b> OAuth client. For an app in testing, add your Gmail account as a test user. Then enter the client details below.</p><a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">Open Google Cloud credentials ↗</a><label for="google-client-id">Desktop OAuth client ID</label><input id="google-client-id" autocomplete="off" placeholder="${status.google_client ? "Leave blank to keep saved client" : "…apps.googleusercontent.com"}" ${status.google_client ? "" : "required"}><label for="google-client-secret">Client secret</label><input id="google-client-secret" type="password" autocomplete="off" placeholder="Leave blank to keep saved secret"><p class="help">Google sign-in opens in your system browser. Only Gmail read-only access is requested, using a local callback and PKCE.</p>`}<p class="help">Stored in ${esc(status.storage)}. Saved credentials are never shown back in this form.</p><div class="error" id="form-error" role="alert"></div><div class="form-actions"><button class="button dark">Save setup securely</button></div></form>`,
  );
  $("#connection-form").onsubmit = async (e) => {
    e.preventDefault();
    const button = e.submitter;
    button.disabled = true;
    try {
      await api("/api/connections", "PUT", {
        canvas_url: canvas ? $("#canvas-url").value : status.canvas_url,
        canvas_token: canvas ? $("#canvas-token").value : "",
        google_client_id: canvas ? "" : $("#google-client-id").value,
        google_client_secret: canvas ? "" : $("#google-client-secret").value,
      });
      modal.close();
      await refresh();
      toast("Connection setup saved.");
    } catch (err) {
      errorInForm(err);
      button.disabled = false;
    }
  };
}
function bindConnections() {
  if ($("#import-course-materials"))
    $("#import-course-materials").onclick = importModal;
  if ($("#setup-canvas"))
    $("#setup-canvas").onclick = () => connectionModal("canvas");
  if ($("#setup-google"))
    $("#setup-google").onclick = () => connectionModal("gmail");
  if ($("#refresh-connections")) $("#refresh-connections").onclick = refresh;
  if ($("#connect-google"))
    $("#connect-google").onclick = async (e) => {
      if (!state.connection_status.google_client) {
        connectionModal("gmail");
        return;
      }
      const button = e.currentTarget;
      button.disabled = true;
      try {
        const response = await api("/api/oauth/google/start", "POST");
        openModal(
          "Connect Gmail with Google.",
          `<p class="help">Continue in your system browser, choose the intended account, and review the Gmail read-only permission. When Google finishes, return to Daybook and refresh the connection status.</p><div class="form-actions"><a class="button dark" href="${esc(response.url)}" target="_blank" rel="noopener noreferrer">Continue to Google ↗</a></div>`,
        );
      } catch (err) {
        toast(err.message);
      } finally {
        button.disabled = false;
      }
    };
  document.querySelectorAll("[data-disconnect]").forEach(
    (el) =>
      (el.onclick = async () => {
        el.disabled = true;
        try {
          await api("/api/connections/" + el.dataset.disconnect, "DELETE");
          await refresh();
          toast("Local connection removed. Imported tasks were kept.");
        } catch (err) {
          el.disabled = false;
          toast(err.message);
        }
      }),
  );
}

function calendarItems(day) {
  const onDay = (d) => d && Dates.dayKey(d, state.timezone) === day;
  return {
    tasks: state.tasks.filter(
      (t) =>
        !t.completed &&
        (calendarCourse === "all" || t.course === calendarCourse) &&
        t.confidence !== "review" &&
        (onDay(t.due_at) || t.due_date === day) &&
        !notebookState.events.some((e) => e.linked_task_id === t.id),
    ),
    events: calendarEventsOn(day),
    blocks: state.blocks.filter((b) => onDay(b.start)),
  };
}
function selectedAgenda() {
  const items = calendarItems(selectedDay);
  return `<aside class="panel day-agenda" id="day-agenda" aria-label="Selected day agenda"><div class="eyebrow">YOUR DAY, IN FOCUS</div><h2 aria-live="polite">${Dates.format(selectedDay, { weekday: "long", month: "long", day: "numeric" })}</h2><p class="help">${items.tasks.length} deadlines · ${items.events.length} events · ${items.blocks.length} blocks</p><div class="day-actions"><button class="button dark" id="day-task">${icon("plus")}Task</button><button class="button" id="busy">Busy time</button><button class="button" id="new-event">Event</button></div>${items.events.length ? `<h3 class="agenda-label">CALENDAR EVENTS</h3>${eventCards(selectedDay)}` : ""}${items.blocks.length ? `<h3 class="agenda-label">TIME BLOCKS</h3>${items.blocks.map((b) => `<button class="agenda-block" data-block="${b.id}"><span>${time(b.start)} – ${time(b.end)}</span><b>${esc(b.title)}</b><small>${b.kind === "work" ? "Work block" : "Busy time"}</small></button>`).join("")}` : ""}${items.tasks.length ? `<h3 class="agenda-label">DEADLINES</h3>${taskList(items.tasks)}` : ""}${!items.tasks.length && !items.events.length && !items.blocks.length ? '<div class="empty"><span class="empty-icon">' + icon("sun") + "</span><h3>A little open space.</h3>No deadlines, events, or time blocks on this day.</div>" : ""}<p class="help agenda-foot">${esc(state.timezone)} · Dates without a time stay date-only.</p></aside>`;
}
function calendarPage() {
  const todayKey = Dates.dayKey(state.now, state.timezone);
  if (!calendarMonth) calendarMonth = todayKey.slice(0, 7) + "-01";
  if (!selectedDay) selectedDay = todayKey;
  const days = Dates.monthDays(calendarMonth);
  return (
    head(
      "A month of possibilities.",
      "See the bigger picture. Choose a day to find your next step.",
      "YOUR CALENDAR",
    ) +
    `<div class="calendar-toolbar"><div class="month-heading"><h2>${Dates.format(calendarMonth, { month: "long", year: "numeric" })}</h2><div class="month-nav"><button class="button" id="prev-month" aria-label="Previous month">←</button><button class="button" id="this-month">Today</button><button class="button" id="next-month" aria-label="Next month">→</button></div></div><div class="calendar-actions"><select id="calendar-course" aria-label="Filter calendar course"><option value="all">All courses & tasks</option>${[...new Set(notebookState.events.map((e) => e.course).filter(Boolean))].map((c) => `<option ${c === calendarCourse ? "selected" : ""}>${esc(c)}</option>`).join("")}</select><button class="button" id="new-cadence">Add cadence</button><a class="button" href="/api/calendar.ics?demo=${demo}" download>Export .ics</a></div></div><div class="month-layout"><section class="month-card" aria-label="Month calendar"><div class="month-weekdays">${["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"].map((d) => `<span>${d}</span>`).join("")}</div><div class="month-grid">${days
      .map((day) => {
        const { tasks, blocks, events } = calendarItems(day);
        const entries = [
          ...events.map((e) => ({
            label: e.title,
            kind:
              e.kind === "break"
                ? "break"
                : e.tentative
                  ? "tentative"
                  : "deadline",
          })),
          ...tasks.map((t) => ({
            label: t.title,
            kind: t.category === "career" ? "career" : "deadline",
          })),
          ...blocks.map((b) => ({ label: b.title, kind: "work" })),
        ];
        const labels = entries
          .slice(0, 2)
          .map(
            (e) => `<span class="month-chip ${e.kind}">${esc(e.label)}</span>`,
          )
          .join("");
        return `<button class="month-day ${day < todayKey ? "is-past" : ""} ${day.slice(0, 7) !== calendarMonth.slice(0, 7) ? "outside" : ""} ${day === todayKey ? "is-today" : ""} ${day === selectedDay ? "selected" : ""}" data-day="${day}" aria-label="${Dates.format(day, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}, ${entries.length} items" aria-pressed="${day === selectedDay}" ${day === todayKey ? 'aria-current="date"' : ""} tabindex="${day === selectedDay ? 0 : -1}"><span class="month-number">${Number(day.slice(-2))}</span><span class="month-items">${labels}${entries.length > 2 ? `<span class="month-more">+${entries.length - 2} more</span>` : ""}</span><span class="month-dots" aria-hidden="true">${entries
          .slice(0, 4)
          .map((e) => `<i class="${e.kind}"></i>`)
          .join("")}</span></button>`;
      })
      .join(
        "",
      )}</div><div class="cal-key month-key"><span><i class="key-square deadline"></i>Academic</span><span><i class="key-square career"></i>Career</span><span><i class="key-square"></i>Time blocks</span></div></section>${selectedAgenda()}</div><p class="help calendar-keyboard">Tip: use arrow keys to move between days; Page Up / Page Down changes the month.</p>`
  );
}
function reminderCard(r) {
  const overdue =
    r.due_at && !r.completed_at && new Date(r.due_at) < new Date(state.now);
  return `<article class="reminder-card ${r.completed_at ? "is-done" : ""}"><div class="reminder-card-top"><span class="reminder-symbol ${r.category}">${icon("bell")}</span><span class="tag ${r.archived ? "" : r.completed_at ? "confirmed" : overdue ? "review" : "expected"}">${r.archived ? "Archived" : r.completed_at ? "Checked in" : overdue ? "Due for a check-in" : "Ready when you are"}</span><button class="icon-button reminder-edit" data-reminder-edit="${r.id}" aria-label="Edit ${esc(r.title)}">${icon("edit")}</button></div><h2>${esc(r.title)}</h2><p class="reminder-description">${esc(r.notes) || "A small check-in to keep things moving."}</p><div class="reminder-meta"><span class="tag ${r.category}">${esc(r.category)}</span><span>${r.minutes} min</span><span>${r.completions} check-in${r.completions === 1 ? "" : "s"} recorded</span></div><p class="help reminder-date">${r.completed_at ? "Last completed " + date(r.completed_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : r.due_at ? "Next check-in " + date(r.due_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "No scheduled date · reusable check-in"}</p><div class="reminder-actions">${r.archived ? `<button class="button" data-reminder-action="restore" data-reminder-id="${r.id}">Restore reminder</button>` : r.completed_at ? `<button class="button dark" data-reminder-action="rearm" data-reminder-id="${r.id}">${icon("refresh")}Ready for next reminder</button><button class="text-button" data-reminder-action="undo" data-reminder-id="${r.id}">Undo check-in</button>` : `<button class="button dark" data-reminder-action="complete" data-reminder-id="${r.id}">${icon("check")}Complete check-in</button>`}</div></article>`;
}
function remindersPage() {
  const list = state.reminders.filter(
    (r) =>
      (reminderFilter === "archived"
        ? r.archived
        : !r.archived &&
          (reminderFilter === "all" ||
            (reminderFilter === "done" ? r.completed_at : !r.completed_at))) &&
      (r.title + " " + r.notes)
        .toLowerCase()
        .includes(reminderSearch.toLowerCase()),
  );
  const ready = state.reminders.filter(
    (r) => !r.archived && !r.completed_at,
  ).length;
  const count = state.reminders.reduce((n, r) => n + r.completions, 0);
  return (
    head(
      "Small check-ins. Steady progress.",
      "Your reusable reminders, with a little space to follow through.",
      "REMINDERS",
    ) +
    `<section class="reminders-intro"><div><span class="brief-label">${icon("bell")} A FAMILIAR RHYTHM</span><h2>Check in. Follow through. Begin again.</h2><p>Complete a reminder when you take action. Choose “Ready for next reminder” to reuse it. Your past check-ins stay in your weekly review.</p></div><div class="reminder-summary"><strong>${ready}</strong><span>ready to act on</span><small>${count} check-ins recorded</small></div></section><div class="section-title reminders-heading"><h2>Your reminders</h2><button class="button dark" id="new-reminder">${icon("plus")}New reminder</button></div><div class="reminder-tools"><div class="tabs" role="group" aria-label="Reminder status">${[
      ["ready", "Ready"],
      ["done", "Checked in"],
      ["all", "All"],
      ["archived", "Archived"],
    ]
      .map(
        ([key, label]) =>
          `<button class="tab ${reminderFilter === key ? "active" : ""}" data-reminder-filter="${key}" aria-pressed="${reminderFilter === key}">${label}</button>`,
      )
      .join(
        "",
      )}</div><input type="search" id="reminder-search" aria-label="Search reminders" placeholder="Find a reminder…" value="${esc(reminderSearch)}"></div><div class="reminder-grid">${list.map(reminderCard).join("") || `<div class="empty reminder-empty">${icon("bell")}<h3>${reminderFilter === "ready" ? "Nothing asking for your attention." : "No reminders in this view."}</h3>Create a check-in for applications, follow-ups, or everyday things.<br><button class="text-button" id="empty-reminder">Create a reminder ${icon("plus")}</button></div>`}</div><p class="help">Reusable check-ins keep their completion history. Mac desktop notifications are optional: Workspace → Reminder Settings.</p>`
  );
}
function weeklyPage() {
  if (!reviewData || reviewData.week_start !== reviewWeek || reviewData.demo !== demo)
    return head("Week done", "") + '<p class="help" role="status">Loading…</p>';
  const r = reviewData;
  const days = new Map();
  for (const e of r.events) {
    const day = e.date_only ? e.completed_at.slice(0,10) : Dates.dayKey(e.completed_at,state.timezone);
    if (!days.has(day)) days.set(day,[]);
    days.get(day).push(e);
  }
  return head("Week done", "") + `<div class="week-navigation"><button class="icon-button" id="review-prev" aria-label="Previous week">←</button><span>${Dates.format(r.week_start,{month:"short",day:"numeric"})} – ${Dates.format(r.week_end,{month:"short",day:"numeric",year:"numeric"})}</span><button class="icon-button" id="review-next" aria-label="Next week">→</button><button class="text-button" id="review-current">This week</button></div><p class="week-total">${r.totals.completed} completed</p>` + ([...days.entries()].sort((a,b)=>b[0].localeCompare(a[0])).map(([day,events])=>`<section class="week-day"><h2>${Dates.format(day,{weekday:"long",month:"short",day:"numeric"})}</h2>${events.map(e=>`<div class="completion-row"><span class="completion-check">${icon("check")}</span><div><b>${esc(e.title)}</b><small>${e.date_only ? "" : time(e.completed_at)}</small></div></div>`).join("")}</section>`).join("") || '<div class="empty">No completed tasks this week.</div>');
}
async function loadWeekly() {
  const requested = ++reviewRequest,
    requestedDemo = demo,
    week = reviewWeek;
  try {
    const data = await api(
      "/api/weekly-review?demo=" + requestedDemo + "&week=" + week,
    );
    if (
      requested !== reviewRequest ||
      view !== "weekly" ||
      demo !== requestedDemo ||
      reviewWeek !== week
    )
      return;
    reviewData = { ...data, demo: requestedDemo };
    render();
  } catch (e) {
    if (requested === reviewRequest && view === "weekly") {
      $("#view").innerHTML =
        '<div class="panel empty"><h2>We couldn’t load this week.</h2><p>' +
        esc(e.message) +
        '</p><button class="button" id="retry-review">Try again</button></div>';
      $("#retry-review").onclick = loadWeekly;
    }
  }
}
function render() {
  if (location.hash !== "#" + view) history.replaceState(null, "", "#" + view);
  document
    .querySelectorAll("[data-icon]")
    .forEach((el) => (el.innerHTML = icon(el.dataset.icon)));
  $("#task-count").textContent = active().length;
  if (view === "weekly" && !reviewWeek)
    reviewWeek = Dates.monday(Dates.dayKey(state.now, state.timezone));
  $("#sync").hidden = view !== "sources";
  for (const badge of document.querySelectorAll(".count")) badge.hidden = badge.textContent === "0";
  for (const s of ["canvas", "gmail"])
    $("#" + s + "-dot").classList.toggle("connected", state.connections[s]);
  document.querySelectorAll(".nav").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === view);
    if (el.dataset.view === view) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  $("#crumb").textContent = {
    done: "Day done",
    today: "Today",
    tasks: "All tasks",
    calendar: "Calendar",
    courses: "My courses",
    review: "Date checks",
    sources: "Sources",
    weekly: "Week done",
  }[view];
  $("#view").innerHTML = {
    today,
    done: donePage,
    tasks: () => tasksPage(),
    calendar: calendarPage,
    sources: sourcesPage,
    weekly: weeklyPage,
  }[view]();
  bind();
  if (
    view === "weekly" &&
    (!reviewData ||
      reviewData.week_start !== reviewWeek ||
      reviewData.demo !== demo)
  )
    loadWeekly();
}
function openModal(title, body) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = body;
  modal.showModal();
}
function errorInForm(e) {
  $("#form-error").textContent = e.message;
}
function datetimeValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function evidence(id) {
  const t = state.tasks.find((t) => t.id === id);
  if (!t) return toast("Task is no longer available.");
  return notebookTaskModal(id);
  openModal(
    t.title,
    `<p class="help">${esc(t.course)} · ${esc(t.destination)} · ${t.minutes} min ${confidence(t)}</p>${t.evidence.map((e) => `<section class="evidence-card"><div class="eyebrow">${esc(e.source_type)} · SOURCE EVIDENCE</div><blockquote>${esc(e.quote)}</blockquote>${e.due_at ? `<p class="help">Candidate date: ${date(e.due_at, { dateStyle: "medium", timeStyle: "short" })}</p>` : ""}${e.source_url ? `<a href="${esc(e.source_url)}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>` : '<p class="help">Example or manually imported source</p>'}</section>`).join("")}${t.changes.map((c) => `<div class="history">${esc(c.message)}</div>`).join("")}<form id="review-form"><label for="review-due">${t.confidence === "review" ? "Confirm the correct deadline" : "Deadline"}</label><input id="review-due" type="datetime-local" value="${datetimeValue(t.due_at)}"><p class="help">Announcement changed the date? Update the deadline here; your original evidence is kept. Entered in your browser’s local timezone. Gradescope completion requires your confirmation.</p><label for="review-minutes">Estimated effort (minutes)</label><input id="review-minutes" type="number" min="5" max="600" value="${t.minutes}" required><div id="form-error" class="error" role="alert"></div><div class="form-actions"><button type="button" id="trash-detail" class="text-button">Move to trash</button><button type="button" id="complete-detail" class="button">${t.completed ? "Mark incomplete" : "Mark complete"}</button><button class="button dark" type="submit">${t.confidence === "review" ? "Confirm & save" : "Save changes"}</button></div></form>`,
  );
  $("#review-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const value = $("#review-due").value;
      await api("/api/tasks/" + id, "PATCH", {
        minutes: Number($("#review-minutes").value),
        ...(value ? { due_at: new Date(value).toISOString() } : {}),
        confirm: t.confidence === "review",
      });
      modal.close();
      await refresh();
      toast("Task updated. Evidence preserved.");
    } catch (e) {
      errorInForm(e);
    }
  };
  $("#trash-detail").onclick = async () => {
    try {
      await api("/api/notebook/tasks/" + id, "DELETE");
      modal.close();
      await refresh();
      toast("Moved to trash. Restore it using the Trash filter in All tasks.");
    } catch (e) {
      errorInForm(e);
    }
  };
  $("#complete-detail").onclick = async () => {
    try {
      await api("/api/tasks/" + id, "PATCH", { completed: !t.completed });
      modal.close();
      await refresh();
      toast(t.completed ? "Task reopened." : "Task completed.");
    } catch (e) {
      errorInForm(e);
    }
  };
}
let importDraft = null;
function importModal() {
  openModal("Import syllabus", `<form id="import-form"><div class="form-row"><div><label for="import-course">Course</label><input id="import-course" required maxlength="100" placeholder="ENGL 1270" value="${esc(importDraft?.course || "")}"></div><div><label for="import-year">Year</label><input id="import-year" type="number" min="2020" max="2100" required value="${importDraft?.year || new Date(state.now).getFullYear()}"></div></div><label for="import-file">PDF (optional)</label><input id="import-file" type="file" accept="application/pdf,.pdf"><label for="import-text">Or paste syllabus text</label><textarea id="import-text" placeholder="11/9 Essay #3 due">${esc(importDraft?.text || "")}</textarea><p class="help">You’ll review the dates before saving. Nothing is added yet. For a complex PDF table, paste dated assignment lines if the preview misses items.</p><div id="form-error" class="error" role="alert"></div><div class="form-actions"><button class="button dark">Preview dates</button></div></form>`);
  $("#import-form").onsubmit = async e => {
    e.preventDefault();
    const button = e.submitter; button.disabled = true;
    importDraft = {course:$("#import-course").value.trim(),year:Number($("#import-year").value),text:$("#import-text").value};
    try {
      const file = $("#import-file").files[0];
      let result;
      if (file) {
        const response = await fetch(`/api/import/pdf-preview?course=${encodeURIComponent(importDraft.course)}&year=${importDraft.year}`, {method:"POST",headers:{"Content-Type":"application/pdf","X-Meridian-Token":state.token},body:file});
        result = await response.json();
        if (!response.ok) throw Error(typeof result.detail === "string" ? result.detail : "Could not read this PDF.");
      } else {
        if (!importDraft.text.trim()) throw Error("Choose a PDF or paste the dated assignment lines.");
        result = await api("/api/import/preview","POST",importDraft);
      }
      showImportPreview(result.items);
    } catch (error) { errorInForm(error); } finally { button.disabled = false; }
  };
}
function showImportPreview(items) {
  $("#modal-title").textContent = "Review import";
  $("#modal-body").innerHTML = `<p class="help">${items.length} possible deadlines. Keep past dates on Calendar; add only work you still need to do as tasks. Blank or uncertain dates are skipped until you fill them in.</p><form id="import-confirm"><div class="import-items">${items.map((item,i) => `<div class="import-item"><label class="import-item-title" for="import-day-${i}">${esc(item.title)}<small>${esc(item.course)}${item.time ? " · " + esc(item.time) : " · date only"}</small></label><input id="import-day-${i}" type="date" aria-label="Date for ${esc(item.title)}" value="${esc(item.date || "")}"><select id="import-mode-${i}" aria-label="Import ${esc(item.title)}"><option value="skip" ${!item.date ? "selected" : ""}>Skip</option><option value="calendar" ${item.date && !item.track ? "selected" : ""}>Calendar only</option><option value="task" ${item.date && item.track ? "selected" : ""}>Task + calendar</option></select><details class="import-evidence"><summary>Source text</summary><p>${esc(item.evidence)}</p></details></div>`).join("") || '<p>No dated assignment lines were found. Try pasting lines with an assignment name and a date.</p>'}</div><div id="form-error" class="error" role="alert"></div><div class="form-actions"><button class="button" type="button" id="import-back">Back</button><button class="button dark" ${items.length ? "" : "disabled"}>Import selected</button></div></form>`;
  $("#import-back").onclick = importModal;
  $("#import-confirm").onsubmit = async e => {
    e.preventDefault(); e.submitter.disabled = true;
    try {
      const selected = items.flatMap((item,i) => {
        const mode = $("#import-mode-" + i).value;
        if (mode === "skip") return [];
        const day = $("#import-day-" + i).value;
        if (!day) throw Error("Choose a date for “" + item.title + "” or set it to Skip.");
        return [{...item,date:day,track:mode === "task"}];
      });
      if (!selected.length) throw Error("Choose at least one item to import.");
      const result = await api("/api/import/commit","POST",{items:selected});
      modal.close(); importDraft = null; view = "calendar"; await refresh();
      toast(`${result.events} calendar dates added · ${result.tasks} tasks added${result.existing ? " · " + result.existing + " already imported" : ""}`);
    } catch (error) { errorInForm(error); e.submitter.disabled = false; }
  };
}
function addModal(defaultDay = null) {
  notebookTaskModal(null, defaultDay);
}
function busyModal(defaultDay = null) {
  openModal(
    "Protect some time.",
    `<form id="busy-form"><label for="busy-title">Class or unavailable time</label><input id="busy-title" required placeholder="e.g. MATH 2210 lecture"><label for="busy-start">Start (browser timezone)</label><input id="busy-start" type="datetime-local" value="${defaultDay ? datetimeValue(Dates.atZone(defaultDay, "09:00", state.timezone)) : ""}" required><label for="busy-minutes">Duration in minutes</label><input id="busy-minutes" type="number" min="5" max="600" value="60" required><p class="help">Busy time is saved to your personal calendar.</p><div id="form-error" class="error" role="alert"></div><div class="form-actions"><button class="button dark">Save busy time</button></div></form>`,
  );
  $("#busy-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/blocks", "POST", {
        title: $("#busy-title").value,
        start: new Date($("#busy-start").value).toISOString(),
        minutes: Number($("#busy-minutes").value),
        kind: "busy",
      });
      modal.close();
      demo = false;
      localStorage.setItem("meridian-demo", "false");
      await refresh();
      toast("Time protected.");
    } catch (e) {
      errorInForm(e);
    }
  };
}
function bind() {
  document.querySelectorAll("[data-restore-task]").forEach(el => el.onclick = async () => {
    try { await api("/api/notebook/tasks/" + el.dataset.restoreTask + "/restore", "POST"); await refresh(); toast("Task restored."); }
    catch (e) { toast(e.message); }
  });
  document.querySelectorAll("[data-view]").forEach(
    (el) =>
      (el.onclick = () => {
        if (!canLeaveReflection()) return;
        view = el.dataset.view;
        if (view === "weekly") reviewData = null;
        filter = "all";
        query = "";
        render();
      }),
  );
  document.querySelectorAll("[data-filter]").forEach(
    (el) =>
      (el.onclick = () => {
        filter = el.dataset.filter;
        render();
      }),
  );
  document
    .querySelectorAll("[data-task]")
    .forEach((el) => (el.onclick = () => evidence(Number(el.dataset.task))));
  document.querySelectorAll("[data-complete]").forEach(
    (el) =>
      (el.onchange = async () => {
        try {
          await api("/api/tasks/" + el.dataset.complete, "PATCH", {
            completed: el.checked,
          });
          await refresh();
          toast(el.checked ? "One thing moved forward." : "Task reopened.");
        } catch (e) {
          el.checked = !el.checked;
          toast(e.message);
        }
      }),
  );
  document.querySelectorAll("[data-course]").forEach(
    (el) =>
      (el.onclick = () => {
        view = "tasks";
        filter = "all";
        query = el.dataset.course;
        render();
      }),
  );
  document.querySelectorAll("[data-block]").forEach(
    (el) =>
      (el.onclick = () => {
        const b = state.blocks.find((b) => b.id === Number(el.dataset.block));
        openModal(
          b.title,
          `<p class="help">${date(b.start, { dateStyle: "medium", timeStyle: "short" })} – ${time(b.end)}<br>${b.kind === "work" ? "Suggested work block. The original deadline will stay in place." : "Class or unavailable time."}</p><div id="form-error" class="error" role="alert"></div><div class="form-actions"><button class="button" id="remove-block">Remove block</button></div>`,
        );
        $("#remove-block").onclick = async () => {
          try {
            await api("/api/blocks/" + b.id, "DELETE");
            modal.close();
            await refresh();
            toast("Block removed.");
          } catch (e) {
            errorInForm(e);
          }
        };
      }),
  );
  if ($("#import")) $("#import").onclick = importModal;
  if ($("#search"))
    $("#search").oninput = (e) => {
      query = e.target.value;
      const pos = e.target.selectionStart;
      render();
      $("#search").focus();
      $("#search").setSelectionRange(pos, pos);
    };
  if ($("#task-filter"))
    $("#task-filter").onchange = (e) => {
      filter = e.target.value;
      render();
    };
  if ($("#plan"))
    $("#plan").onclick = async (e) => {
      e.currentTarget.disabled = true;
      try {
        const r = await api("/api/plan?demo=" + demo, "POST");
        await refresh();
        toast(
          r.scheduled
            ? `${r.scheduled} focused work blocks added to today.`
            : "No new blocks fit today. Existing plans and deadlines were preserved.",
        );
      } catch (e) {
        toast(e.message);
        render();
      }
    };
  bindWorkspace();
  bindConnections();
  bindNotebook();
  if ($("#more-tasks"))
    $("#more-tasks").onclick = () => {
      taskLimit += 60;
      render();
    };
}
$("#close-modal").onclick = () => modal.close();
$("#add-task").onclick = () => addModal();
$("#sync").onclick = async () => {
  try {
    await api("/api/sync/start", "POST");
    await refresh();
    toast("30-day Gmail import started. Progress is saved as it runs.");
  } catch (e) {
    toast(e.message);
  }
};
function reminderModal(id = null, defaultDay = null) {
  const reminder = id ? state.reminders.find((r) => r.id === id) : null;
  const due =
    reminder?.due_at ||
    (defaultDay ? Dates.atZone(defaultDay, "17:00", state.timezone) : null);
  openModal(
    reminder ? "Make this check-in yours." : "A reminder worth returning to.",
    `<form id="reminder-form"><label for="reminder-title">Reminder title</label><input id="reminder-title" required maxlength="250" value="${esc(reminder?.title || "")}" placeholder="e.g. Follow up on internship applications"><label for="reminder-notes">A little context</label><textarea id="reminder-notes" maxlength="4000" placeholder="What does following through look like?">${esc(reminder?.notes || "")}</textarea><div class="form-row"><div><label for="reminder-category">Category</label><select id="reminder-category">${["career", "academic", "personal"].map((c) => `<option value="${c}" ${c === (reminder?.category || "career") ? "selected" : ""}>${c[0].toUpperCase() + c.slice(1)}</option>`).join("")}</select></div><div><label for="reminder-minutes">Estimated minutes</label><input id="reminder-minutes" type="number" min="5" max="600" value="${reminder?.minutes || 15}" required></div></div><label for="reminder-due">Next check-in (optional, browser timezone)</label><input id="reminder-due" type="datetime-local" value="${datetimeValue(due)}"><p class="help">${demo ? "Editing example data. Switch off Demo workspace for your own reminders." : "Saved to your personal workspace."} Reusing this check-in keeps earlier completions. No notification is scheduled.</p><div id="form-error" class="error" role="alert"></div><div class="form-actions">${reminder ? `<button class="button" type="button" id="archive-reminder">${reminder.archived ? "Restore reminder" : "Archive reminder"}</button>` : ""}<button class="button dark" type="submit">${reminder ? "Save reminder" : "Create reminder"}</button></div></form>`,
  );
  $("#reminder-form").onsubmit = async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      const value = $("#reminder-due").value;
      await api(
        "/api/reminders" + (id ? "/" + id : "") + "?demo=" + demo,
        id ? "PUT" : "POST",
        {
          title: $("#reminder-title").value,
          notes: $("#reminder-notes").value,
          category: $("#reminder-category").value,
          minutes: Number($("#reminder-minutes").value),
          due_at: value ? new Date(value).toISOString() : null,
        },
      );
      modal.close();
      await refresh();
      toast("Reminder saved.");
    } catch (err) {
      errorInForm(err);
      e.submitter.disabled = false;
    }
  };
  if ($("#archive-reminder"))
    $("#archive-reminder").onclick = async (e) => {
      const button = e.currentTarget;
      button.disabled = true;
      try {
        await api("/api/reminders/" + id + "/action?demo=" + demo, "POST", {
          action: reminder.archived ? "restore" : "archive",
        });
        modal.close();
        await refresh();
        toast(
          reminder.archived
            ? "Reminder restored."
            : "Reminder archived. Its history is preserved.",
        );
      } catch (err) {
        errorInForm(err);
        button.disabled = false;
      }
    };
}
function reflectionKey() {
  return `meridian-reflection-${demo ? "demo" : "personal"}-${reviewWeek}`;
}
function reflectionDraft() {
  try {
    return JSON.parse(localStorage.getItem(reflectionKey()) || "null");
  } catch {
    return null;
  }
}
function canLeaveReflection() {
  if ($("#reflection-form")) {
    const notes = {
      wins: $("#reflection-wins").value,
      friction: $("#reflection-friction").value,
      next_focus: $("#reflection-next").value,
    };
    const saved = reviewData?.notes;
    if (
      saved &&
      ["wins", "friction", "next_focus"].some((k) => notes[k] !== saved[k])
    )
      localStorage.setItem(reflectionKey(), JSON.stringify(notes));
    else localStorage.removeItem(reflectionKey());
  }
  return true;
}
function selectCalendarDay(day, focus = true, reveal = false) {
  selectedDay = day;
  calendarMonth = day.slice(0, 7) + "-01";
  render();
  if (focus)
    document
      .querySelector(`[data-day="${day}"]`)
      ?.focus({ preventScroll: true });
  if (reveal && window.matchMedia("(max-width:1250px)").matches) {
    $(".day-agenda").scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion:reduce)").matches
        ? "auto"
        : "smooth",
      block: "start",
    });
  }
}
function bindWorkspace() {
  document.querySelectorAll("[data-day]").forEach((el) => {
    el.onclick = () => selectCalendarDay(el.dataset.day, true, true);
    el.onkeydown = (e) => {
      const day = el.dataset.day;
      const movements = {
        ArrowLeft: -1,
        ArrowRight: 1,
        ArrowUp: -7,
        ArrowDown: 7,
      };
      let target;
      if (e.key in movements) target = Dates.addDays(day, movements[e.key]);
      if (e.key === "Home") target = Dates.monday(day);
      if (e.key === "End") target = Dates.addDays(Dates.monday(day), 6);
      if (e.key === "PageUp") target = Dates.shiftMonth(day, -1);
      if (e.key === "PageDown") target = Dates.shiftMonth(day, 1);
      if (target) {
        e.preventDefault();
        selectCalendarDay(target);
      }
    };
  });
  if ($("#prev-month"))
    $("#prev-month").onclick = () =>
      selectCalendarDay(Dates.shiftMonth(selectedDay, -1), false);
  if ($("#next-month"))
    $("#next-month").onclick = () =>
      selectCalendarDay(Dates.shiftMonth(selectedDay, 1), false);
  if ($("#this-month"))
    $("#this-month").onclick = () =>
      selectCalendarDay(Dates.dayKey(state.now, state.timezone), false);
  if ($("#day-task")) $("#day-task").onclick = () => addModal(selectedDay);
  if ($("#day-reminder"))
    $("#day-reminder").onclick = () => reminderModal(null, selectedDay);
  if ($("#busy")) $("#busy").onclick = () => busyModal(selectedDay);
  for (const id of ["new-reminder", "empty-reminder"])
    if ($("#" + id)) $("#" + id).onclick = () => reminderModal();
  document
    .querySelectorAll("[data-reminder-edit]")
    .forEach(
      (el) =>
        (el.onclick = () => reminderModal(Number(el.dataset.reminderEdit))),
    );
  document.querySelectorAll("[data-reminder-filter]").forEach(
    (el) =>
      (el.onclick = () => {
        reminderFilter = el.dataset.reminderFilter;
        render();
      }),
  );
  if ($("#reminder-search"))
    $("#reminder-search").oninput = (e) => {
      reminderSearch = e.target.value;
      const pos = e.target.selectionStart;
      render();
      $("#reminder-search").focus();
      $("#reminder-search").setSelectionRange(pos, pos);
    };
  document.querySelectorAll("[data-reminder-action]").forEach(
    (el) =>
      (el.onclick = async () => {
        el.disabled = true;
        try {
          const action = el.dataset.reminderAction;
          await api(
            "/api/reminders/" + el.dataset.reminderId + "/action?demo=" + demo,
            "POST",
            { action },
          );
          if (action === "complete") reminderFilter = "done";
          if (action === "rearm" || action === "undo" || action === "restore")
            reminderFilter = "ready";
          reviewData = null;
          await refresh();
          toast(
            {
              complete: "Check-in recorded. One thing moved forward.",
              rearm:
                "Ready again. Previous check-ins stay in your weekly review.",
              undo: "Check-in undone.",
              restore: "Reminder restored.",
            }[action],
          );
        } catch (err) {
          el.disabled = false;
          toast(err.message);
        }
      }),
  );
  function changeReview(day) {
    canLeaveReflection();
    reviewWeek = day;
    reviewData = null;
    render();
  }
  if ($("#review-prev"))
    $("#review-prev").onclick = () =>
      changeReview(Dates.addDays(reviewWeek, -7));
  if ($("#review-next"))
    $("#review-next").onclick = () =>
      changeReview(Dates.addDays(reviewWeek, 7));
  if ($("#review-current"))
    $("#review-current").onclick = () =>
      changeReview(Dates.monday(Dates.dayKey(state.now, state.timezone)));
  if ($("#reflection-form")) {
    $("#reflection-form").oninput = () => {
      canLeaveReflection();
      $("#reflection-status").textContent =
        "Draft saved in this browser · Save reflection to keep it in your workspace";
    };
    $("#reflection-form").onsubmit = async (e) => {
      e.preventDefault();
      const form = e.currentTarget,
        button = e.submitter;
      const savedWeek = reviewWeek,
        savedDemo = demo,
        draftKey = reflectionKey();
      button.disabled = true;
      const notes = {
        wins: $("#reflection-wins").value,
        friction: $("#reflection-friction").value,
        next_focus: $("#reflection-next").value,
      };
      try {
        await api(
          "/api/weekly-review/" + savedWeek + "?demo=" + savedDemo,
          "PUT",
          notes,
        );
        const draft = localStorage.getItem(draftKey);
        if (!draft || draft === JSON.stringify(notes))
          localStorage.removeItem(draftKey);
        if (
          view === "weekly" &&
          reviewWeek === savedWeek &&
          demo === savedDemo &&
          $("#reflection-form") === form
        ) {
          reviewData.notes = { ...notes, updated_at: new Date().toISOString() };
          const edited = ["wins", "friction", "next_focus"].some(
            (k) =>
              $(
                "#reflection-" +
                  { wins: "wins", friction: "friction", next_focus: "next" }[k],
              ).value !== notes[k],
          );
          $("#reflection-status").textContent = edited
            ? "Earlier version saved · You have a newer draft"
            : "Reflection saved to your workspace.";
          $("#reflection-error").textContent = "";
        }
        toast("A little perspective, saved.");
      } catch (err) {
        if ($("#reflection-form") === form)
          $("#reflection-error").textContent = err.message;
        else
          toast(
            "Reflection was not saved. Your draft is still in this browser.",
          );
      } finally {
        button.disabled = false;
      }
    };
  }
}

// Advance the local day even when the app stays open overnight or the Mac wakes.
let pendingDayRender = false;
function updateCurrentDay() {
  if (!state) return;
  const now = new Date().toISOString();
  const shift = Dates.rollover(state.now, now, state.timezone, selectedDay, calendarMonth);
  state.now = now;
  if (shift.changed) {
    selectedDay = shift.selection;
    calendarMonth = shift.month;
    if (reviewWeek === Dates.monday(shift.previousDay))
      reviewWeek = Dates.monday(shift.today);
    reviewData = null;
    pendingDayRender = true;
  }
  if (!pendingDayRender || modal.open || document.activeElement?.matches("input, textarea, select")) return;
  pendingDayRender = false;
  render();
}
setInterval(updateCurrentDay, 30000);
window.addEventListener("focus", updateCurrentDay);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) updateCurrentDay();
});
modal.addEventListener("close", updateCurrentDay);

// Poll only status while editing so forms and reflection drafts never lose focus.
setInterval(async () => {
  if (!state) return;
  try {
    const p = await api("/api/sync/progress");
    const wasRunning = state.syncProgress?.running;
    state.syncProgress = p;
    if (view === "sources" && !modal.open) {
      $("#view").innerHTML = sourcesPage();
      bind();
    }
    if (wasRunning && !p.running && !modal.open && view !== "weekly")
      await refresh();
  } catch {}
}, 10000);
// WKWebView may navigate between fragments without reloading the document.
window.addEventListener("hashchange", () => {
  const target = location.hash.slice(1);
  if (!state || target === view || !availableViews.has(target)) return;
  canLeaveReflection();
  modal.close();
  view = target;
  filter = "all";
  query = "";
  reviewData = null;
  render();
});
refresh();
