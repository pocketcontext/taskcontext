import { it, expect } from "vitest";
import { app, dateOnly, subtitle, type Entity } from "./config";
import schema from "./schema.snapshot.json";
it("every browser field and relation target belongs to the exported SQL schema", () => {
  for (const e of app.entities) {
    const table = schema.tables.find((t) => t.name === e.table);
    expect(table, e.table).toBeDefined();
    const names = table!.columns.map((c) => c.name);
    for (const f of [
      ...e.title,
      ...e.search,
      ...(e.subtitle || []),
      ...(e.markdown || []),
      ...(e.dates || []),
      ...Object.keys(e.filters || {}),
      ...Object.keys(e.relations || {}),
    ])
      expect(names, `${e.table}.${f}`).toContain(f);
    for (const target of Object.values(e.relations || {}))
      expect(
        app.entities.some((t) => t.table === target),
        target,
      ).toBe(true);
    expect(["users", "agents", "_superusers"]).not.toContain(e.table);
  }
});
it("shows the optional issue due date as a calendar date", () => {
  const issues = app.entities.find((e) => e.table === "issues") as Entity;
  expect(issues.dates).toContain("due_date");
  expect(dateOnly("2026-11-01 00:00:00.000Z")).toBe("2026-11-01");
  expect(dateOnly("2026-11-01T23:30:00Z")).toBe("2026-11-01");
  expect(dateOnly("not a date")).toBe("not a date");
  expect(
    subtitle(issues, {
      status: "ready",
      priority: "high",
      due_date: "2026-11-01 00:00:00.000Z",
    }),
  ).toBe("ready · high · Due date 2026-11-01");
  expect(
    subtitle(issues, { status: "ready", priority: "high", due_date: "" }),
  ).toBe("ready · high");
});
