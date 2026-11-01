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
