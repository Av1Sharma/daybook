/* Calendar-only arithmetic uses ISO date keys and UTC to avoid browser/DST drift. */
(function (root) {
  "use strict";
  const iso = (value) => value.toISOString().slice(0, 10);
  const parse = (day) => new Date(day + "T12:00:00Z");
  const addDays = (day, n) => {
    const d = parse(day);
    d.setUTCDate(d.getUTCDate() + n);
    return iso(d);
  };
  function dayKey(instant, zone) {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-US", {
        timeZone: zone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      })
        .formatToParts(new Date(instant))
        .map((p) => [p.type, p.value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}`;
  }
  function rollover(previousInstant, instant, zone, selection, month) {
    const previousDay = dayKey(previousInstant, zone);
    const today = dayKey(instant, zone);
    const followingToday = !selection || selection === previousDay;
    const changed = previousDay !== today;
    return {
      changed,
      previousDay,
      today,
      selection: changed && followingToday ? today : selection,
      month: changed && followingToday && (!month || month.slice(0, 7) === previousDay.slice(0, 7))
        ? today.slice(0, 7) + "-01" : month,
    };
  }
  function shiftMonth(day, n) {
    const d = parse(day),
      date = d.getUTCDate();
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + n);
    const last = new Date(
      Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0),
    ).getUTCDate();
    d.setUTCDate(Math.min(date, last));
    return iso(d);
  }
  function monday(day) {
    const d = parse(day);
    return addDays(day, -((d.getUTCDay() + 6) % 7));
  }
  function monthDays(day) {
    const first = day.slice(0, 7) + "-01",
      start = monday(first);
    return Array.from({ length: 42 }, (_, i) => addDays(start, i));
  }
  function format(day, options) {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "UTC",
      ...options,
    }).format(parse(day));
  }
  function atZone(day, clock, zone) {
    const target = new Date(`${day}T${clock}:00Z`);
    let guess = new Date(target);
    for (let i = 0; i < 3; i++) {
      const p = Object.fromEntries(
        new Intl.DateTimeFormat("en-US", {
          timeZone: zone,
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hourCycle: "h23",
        })
          .formatToParts(guess)
          .map((p) => [p.type, p.value]),
      );
      const observed = new Date(
        `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:00Z`,
      );
      guess = new Date(guess.getTime() + target.getTime() - observed.getTime());
    }
    return guess.toISOString();
  }
  const api = {
    addDays,
    dayKey,
    rollover,
    shiftMonth,
    monday,
    monthDays,
    format,
    atZone,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MeridianDates = api;
})(globalThis);
