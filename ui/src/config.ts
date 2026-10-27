export interface Entity {
  table: string;
  label: string;
  title: string[];
  subtitle?: string[];
  search: string[];
  filters?: Record<string, string[]>;
  relations?: Record<string, string>;
  hidden?: string[];
  markdown?: string[];
  dates?: string[];
  menu?: boolean;
  relationLabels?: Record<string, string>;
  reverseLabels?: Record<string, string>;
}
export const app: {
  name: string;
  authCollection: string;
  google?: boolean;
  entities: Entity[];
} = {
  name: "TaskContext",
  authCollection: "users",
  entities: [
    {
      table: "issues",
      label: "Issues",
      title: ["key", "title"],
      subtitle: ["status", "priority", "due_date"],
      search: ["key", "title", "description"],
      filters: {
        status: ["backlog", "ready", "in_progress", "review", "done"],
        priority: ["low", "medium", "high", "urgent"],
      },
      relations: {
        project: "projects",
        parent: "issues",
        assignee: "user_directory",
        reporter: "user_directory",
      },
      markdown: ["description"],
      dates: ["due_date"],
    },
    {
      table: "projects",
      label: "Projects",
      title: ["key", "name"],
      search: ["key", "name", "description"],
      filters: { archived: ["0", "1"] },
      markdown: ["description"],
    },
    {
      table: "comments",
      label: "Comments",
      title: ["body"],
      search: ["body"],
      relations: { issue: "issues" },
      markdown: ["body"],
    },
    {
      table: "references",
      label: "Evidence",
      title: ["title"],
      subtitle: ["kind"],
      search: ["title", "url"],
      relations: { issue: "issues" },
    },
    {
      table: "issue_links",
      label: "Dependencies",
      title: ["type"],
      subtitle: ["active"],
      search: ["type"],
      filters: {
        active: ["1", "0"],
        type: ["blocks", "relates", "duplicates"],
      },
      relations: { source: "issues", target: "issues" },
      relationLabels: { source: "Source issue", target: "Target issue" },
      reverseLabels: {
        source: "Outgoing dependencies",
        target: "Incoming dependencies",
      },
    },
    {
      table: "user_directory",
      label: "People",
      title: ["name"],
      search: ["name"],
      menu: false,
    },
  ],
};
for (const e of app.entities)
  if (e.table !== "user_directory")
    e.relations = {
      ...e.relations,
      created_by: "user_directory",
      updated_by: "user_directory",
    };
// PocketBase date fields read through SQL as "YYYY-MM-DD HH:MM:SS.sssZ"; show the calendar date only.
export const dateOnly = (value: unknown) =>
  typeof value === "string"
    ? (/^(\d{4}-\d{2}-\d{2})(?:[ T]|$)/.exec(value)?.[1] ?? value)
    : String(value);
export const subtitle = (e: Entity, r: Record<string, unknown>) =>
  (e.subtitle || [])
    .filter((f) => r[f] !== null && r[f] !== undefined && r[f] !== "")
    .map((f) =>
      e.dates?.includes(f)
        ? `${f.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase())} ${dateOnly(r[f])}`
        : String(r[f]),
    )
    .join(" · ");
