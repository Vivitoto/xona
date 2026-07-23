import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  media_root: string;
  source_dir: string;
  destination_dir: string;
  nested_destination_dir: string;
  xchina_cache_dir: string;
  safety_cache_dir: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("Settings saves exact connector, mapping, template, threshold, and asset policy values", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);
  const flareSolverrEndpoint = "http://solver.fixture.local:8191/custom/v1?exact=1";
  const proxyURL = "socks5://proxy.fixture.local:9050";

  await page.goto("/");
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(activePage(page).getByRole("heading", { name: "Settings" })).toBeVisible();

  await page.getByRole("textbox", { name: /Storage roots/ }).fill(fixture.media_root);
  await page.getByLabel("Exact FlareSolverr endpoint").fill(flareSolverrEndpoint);
  await page.getByLabel("Proxy URL").fill(proxyURL);
  await page.getByLabel("XChina cache directory").fill(fixture.xchina_cache_dir);
  await page.getByLabel("Enable Emby notification").check();
  await page.getByLabel("Emby server URL").fill("http://emby.fixture.local:8096");
  await page.getByLabel("Emby API key").fill("emby-fixture-key");
  await page.getByRole("button", { name: "Add mapping" }).click();
  await page.getByLabel("Container root").fill(fixture.media_root);
  await page.getByLabel("Emby visible root").fill("/emby/fixture-media");
  await page.getByLabel("Folder templates").fill("{studio}\n{series}\n{title}");
  await page.getByLabel("Filename template").fill("{xchina_id} - {title} [{release_date}]");
  await page.getByLabel("Asset policy").selectOption("strict");
  await page.getByLabel("Confidence threshold").fill("87");
  await page.getByLabel("Safety cache directory").fill(fixture.safety_cache_dir);
  await page.getByRole("button", { name: "Save settings" }).click();

  await expect(page.getByText("Settings saved")).toBeVisible();
  await page.getByRole("button", { name: "Dashboard" }).click();
  await page.getByRole("button", { name: "Settings" }).click();

  await expect(page.getByLabel("Exact FlareSolverr endpoint")).toHaveValue(
    flareSolverrEndpoint,
  );
  await expect(page.getByLabel("Proxy URL")).toHaveValue(proxyURL);
  await expect(page.getByLabel("Container root")).toHaveValue(fixture.media_root);
  await expect(page.getByLabel("Emby visible root")).toHaveValue("/emby/fixture-media");
  await expect(page.getByLabel("Folder templates")).toHaveValue(
    "{studio}\n{series}\n{title}",
  );
  await expect(page.getByLabel("Filename template")).toHaveValue(
    "{xchina_id} - {title} [{release_date}]",
  );
  await expect(page.getByLabel("Asset policy")).toHaveValue("strict");
  await expect(page.getByLabel("Confidence threshold")).toHaveValue("87");
  await expectNoClippedCriticalText(page);
});

test("Automatic Monitors creates a rule, excludes nested destinations, scans now, and shows review-required items", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);

  await page.goto("/");
  await page.getByRole("button", { name: "Automatic Monitors" }).click();
  await expect(activePage(page).getByRole("heading", { name: "Automatic Monitors" })).toBeVisible();

  await page.getByLabel("Source directory").fill(fixture.source_dir);
  await page.getByLabel("Destination directory").fill(fixture.nested_destination_dir);
  await expect(
    page.getByText(/Destination is inside the watched source/),
  ).toBeVisible();
  await expect(page.getByLabel("Excluded destination prefixes")).toHaveValue(
    fixture.nested_destination_dir,
  );

  await page.getByLabel("Confidence threshold").fill("88");
  await page.getByLabel("Asset policy").selectOption("strict");
  await page.getByRole("button", { name: "Create watch rule" }).click();
  await expect(page.getByText("Watch rule rule-1 saved")).toBeVisible();
  await expect(page.getByRole("table", { name: "Automatic monitor rules" })).toContainText(
    fixture.nested_destination_dir,
  );

  await page.getByRole("button", { name: "Scan now" }).click();
  await expect(page.getByText(/Scan queued for rule-1:/)).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Monitor review-required jobs" }),
  ).toContainText("Monitor review item");
  await expect(
    page.getByRole("table", { name: "Monitor review-required jobs" }),
  ).toContainText("strict_assets_missing");
  await expectNoOverlappingControls(page);
});

test("critical controls remain readable on current viewport", async ({ page, request }) => {
  await resetFixture(request);
  await page.goto("/");

  for (const name of [
    "Dashboard",
    "Manual Organizer",
    "Automatic Monitors",
    "Review Queue",
    "Task Center",
    "Actor Library",
    "History/Rollback",
    "Settings",
  ]) {
    await page.getByRole("button", { name }).click();
    await expect(activePage(page).getByRole("heading", { name })).toBeVisible();
    await expectNoOverlappingControls(page);
    await expectNoClippedCriticalText(page);
  }
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
      const controls = visibleBoxes(nodes);
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

      function visibleBoxes(elements: Element[]) {
        return elements
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
      }
    },
  );
  expect(overlaps).toEqual([]);
}

async function expectNoClippedCriticalText(page: Page) {
  const clipped = await page.locator("button, .field-label, .status").evaluateAll(
    (nodes) =>
      nodes
        .filter((node) => {
          const rect = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            (node.scrollWidth > node.clientWidth + 1 ||
              node.scrollHeight > node.clientHeight + 1)
          );
        })
        .map((node) => node.textContent?.trim() || node.getAttribute("aria-label") || node.tagName)
        .slice(0, 5),
  );
  expect(clipped).toEqual([]);
}
