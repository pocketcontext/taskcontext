import { test, expect } from "@playwright/test";
const id = "record000000001";
const project = "project00000001";
test.beforeEach(async ({ page }) => {
  await page.route("**/api/collections/users/auth-with-password", (route) =>
    route.fulfill({
      json: {
        token:
          "test." +
          Buffer.from(JSON.stringify({ exp: 4102444800 })).toString(
            "base64url",
          ) +
          ".test",
        record: {
          id: "user00000000001",
          collectionName: "users",
          name: "Test",
        },
      },
    }),
  );
  await page.route("**/api/context/query", (route) => {
    const sql = route.request().postDataJSON().sql;
    let rows: any[] = [];
    if (sql.includes('FROM "issues"')) {
      if (sql.includes("OFFSET 30"))
        rows = [{ id: "record000000031", key: "APP-31", title: "Last result" }];
      else if (sql.includes("instr(") && sql.includes("missing")) rows = [];
      else if (sql.includes("WHERE id="))
        rows = [
          {
            id,
            key: "APP-1",
            title: "Reader test",
            description:
              "**Safe** [bad](javascript:alert(1)) <script>window.evil=true</script>",
            project,
            status: "ready",
          },
        ];
      else
        rows = Array.from({ length: 31 }, (_, i) => ({
          id: i ? id.slice(0, 12) + String(i).padStart(3, "0") : id,
          key: "APP-" + (i + 1),
          title: "Reader test " + i,
        }));
    }
    if (sql.includes('FROM "projects"') && sql.includes("WHERE id="))
      rows = [{ id: project, key: "APP", name: "Example project" }];
    const columns = rows.length ? Object.keys(rows[0]) : [];
    return route.fulfill({
      json: {
        columns,
        rows: rows.map((r) => columns.map((c) => r[c])),
        truncated: false,
      },
    });
  });
});
test("deep link survives sign in, related labels resolve and markdown stays inert", async ({
  page,
}) => {
  await page.goto("/#/issues/" + id);
  await page.getByLabel("Email", { exact: true }).fill("test@example.com");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "APP-1 · Reader test", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "APP · Example project", exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => Boolean((window as any).evil))).toBe(false);
  await expect(page.locator('a[href^="javascript:"]')).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "APP-1 · Reader test", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "APP · Example project", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp("/projects/" + project));
});
test("search is server-paginated and mobile browse is usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/issues");
  await page.getByLabel("Email", { exact: true }).fill("test@example.com");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Browse", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("APP-31 · Last result")).toBeVisible();
  await page.getByLabel("Search issues").fill("missing");
  await expect(page.getByText("No matching records.")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
