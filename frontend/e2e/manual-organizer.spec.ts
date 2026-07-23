import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  source_dir: string;
  destination_dir: string;
  sample_file: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("Manual Organizer scans, searches, previews assets, and executes preview/copy modes", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);

  await page.goto("/");
  await page.getByRole("button", { name: "Manual Organizer" }).click();
  await expect(activePage(page).getByRole("heading", { name: "Manual Organizer" })).toBeVisible();

  await page.getByLabel("Source directory").fill(fixture.source_dir);
  await page.getByRole("button", { name: "Scan source" }).click();
  await expect(page.getByText("Scanned 1 item(s)")).toBeVisible();
  await expect(page.getByRole("table", { name: "Scanned jobs" })).toContainText(
    "Sample Work Alpha",
  );

  await page.getByLabel("Pasted filename search").fill("Sample.Work.Alpha.2026.mkv");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Found 2 candidate(s)")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sample Work Alpha" })).toBeVisible();
  const firstCandidate = page.locator(".candidate-card", { hasText: "Sample Work Alpha" }).first();
  await expect(firstCandidate.getByLabel("Score breakdown")).toContainText("title: 60");
  await expect(firstCandidate.getByLabel("Score breakdown")).toContainText("actors: 20");

  await page.getByRole("button", { name: "Select candidate" }).first().click();
  await expect(page.getByText("Candidate accepted")).toBeVisible();

  await page.getByLabel("Destination root").fill(fixture.destination_dir);
  await page.getByLabel("Organization mode").selectOption("preview");
  await page.getByRole("button", { name: "Preview operation plan" }).click();
  await expect(page.getByLabel("Operation plan")).toContainText("Mode preview");
  await expect(page.getByLabel("Operation plan")).toContainText("Materialized assets");
  await expect(page.getByLabel("Operation plan")).toContainText("poster.png");

  await page.getByRole("button", { name: "Execute approved preview" }).click();
  await expect(page.getByText(/Plan fixture-plan-\d+ is previewed/)).toBeVisible();

  await page.getByLabel("Organization mode").selectOption("copy");
  await page.getByRole("button", { name: "Preview operation plan" }).click();
  await expect(page.getByLabel("Operation plan")).toContainText("Mode copy");
  await expect(page.getByLabel("Operation plan")).toContainText(
    "XC-001 - Sample Work Alpha.mkv",
  );

  await page.getByRole("button", { name: "Execute approved preview" }).click();
  await expect(page.getByText(/Plan fixture-plan-\d+ is completed/)).toBeVisible();
  await expectNoOverlappingControls(page);
});

function activePage(page: Page) {
  return page.locator(".page-header");
}

async function resetFixture(request: APIRequestContext): Promise<FixturePaths> {
  const response = await request.post(`${backendURL}/api/e2e/reset`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as FixturePaths;
}

async function expectNoOverlappingControls(page: Page) {
  const overlaps = await page.locator("button, input, select, textarea").evaluateAll(
    (nodes) => {
      const controls = nodes
        .map((node) => {
          const rect = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          return {
            label: node.textContent?.trim() || node.getAttribute("aria-label") || node.tagName,
            visible:
              rect.width > 0 &&
              rect.height > 0 &&
              style.display !== "none" &&
              style.visibility !== "hidden",
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          };
        })
        .filter((entry) => entry.visible);
      const failures: string[] = [];
      for (let index = 0; index < controls.length; index += 1) {
        for (let next = index + 1; next < controls.length; next += 1) {
          const horizontal =
            Math.min(controls[index].right, controls[next].right) -
            Math.max(controls[index].left, controls[next].left);
          const vertical =
            Math.min(controls[index].bottom, controls[next].bottom) -
            Math.max(controls[index].top, controls[next].top);
          if (horizontal > 1 && vertical > 1) {
            failures.push(`${controls[index].label} overlaps ${controls[next].label}`);
          }
        }
      }
      return failures.slice(0, 5);
    },
  );
  expect(overlaps).toEqual([]);
}
