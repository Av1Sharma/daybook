const test = require("node:test");
const assert = require("node:assert/strict");
const D = require("../meridian/static/calendar.js");
test("month grid contains all leap-year days, starting Monday", () => {
  const days = D.monthDays("2028-02-01");
  assert.equal(days.length, 42);
  assert.equal(days[0], "2028-01-31");
  assert.ok(days.includes("2028-02-29"));
  assert.equal(new Set(days).size, 42);
  assert.equal(days[41], "2028-03-12");
});
test("month shifts clamp dates and cross year boundaries", () => {
  assert.equal(D.shiftMonth("2026-01-31", 1), "2026-02-28");
  assert.equal(D.shiftMonth("2028-01-31", 1), "2028-02-29");
  assert.equal(D.shiftMonth("2026-12-31", 1), "2027-01-31");
  assert.equal(D.shiftMonth("2026-01-05", -1), "2025-12-05");
});
test("date arithmetic is independent of DST and browser timezone", () => {
  assert.equal(D.addDays("2026-11-01", 1), "2026-11-02");
  assert.equal(D.addDays("2026-03-08", -1), "2026-03-07");
  assert.equal(D.monday("2026-11-01"), "2026-10-26");
  assert.equal(
    D.dayKey("2026-11-02T02:00:00Z", "America/New_York"),
    "2026-11-01",
  );
  assert.equal(D.dayKey("2026-11-02T02:00:00Z", "Asia/Tokyo"), "2026-11-02");
});
test("selected day defaults resolve in application timezone across DST", () => {
  assert.equal(
    D.atZone("2026-10-31", "17:00", "America/New_York"),
    "2026-10-31T21:00:00.000Z",
  );
  assert.equal(
    D.atZone("2026-11-01", "17:00", "America/New_York"),
    "2026-11-01T22:00:00.000Z",
  );
  assert.equal(
    D.atZone("2026-11-01", "09:00", "Asia/Tokyo"),
    "2026-11-01T00:00:00.000Z",
  );
});
test("date labels do not drift when date is formatted", () => {
  assert.equal(D.format("2026-11-01", { weekday: "long" }), "Sunday");
  assert.equal(
    D.format("2026-01-01", { year: "numeric", month: "long" }),
    "January 2026",
  );
});
test("midnight rollover follows today across month and year boundaries", () => {
  const r = D.rollover("2026-12-31T23:59:00-05:00", "2027-01-01T00:01:00-05:00", "America/New_York", "2026-12-31", "2026-12-01");
  assert.equal(r.changed, true);
  assert.equal(r.today, "2027-01-01");
  assert.equal(r.selection, "2027-01-01");
  assert.equal(r.month, "2027-01-01");
});
test("rollover preserves a manually selected day and browsed month", () => {
  const r = D.rollover("2026-11-01T23:59:00-05:00", "2026-11-02T00:01:00-05:00", "America/New_York", "2026-10-20", "2026-10-01");
  assert.equal(r.changed, true);
  assert.equal(r.selection, "2026-10-20");
  assert.equal(r.month, "2026-10-01");
});
test("DST changes do not advance the calendar until local midnight", () => {
  const r = D.rollover("2026-11-01T01:59:00-04:00", "2026-11-01T01:01:00-05:00", "America/New_York", "2026-11-01", "2026-11-01");
  assert.equal(r.changed, false);
  assert.equal(r.selection, "2026-11-01");
  const wake = D.rollover("2026-11-01T12:00:00-05:00", "2026-11-04T08:00:00-05:00", "America/New_York", "2026-11-01", "2026-11-01");
  assert.equal(wake.selection, "2026-11-04");
});
