import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("Actor Library filters missing images, edits aliases, uploads portrait bytes, and syncs Emby", async ({
  page,
  request,
}) => {
  await resetFixture(request);

  await page.goto("/");
  await page.getByRole("button", { name: "Actor Library" }).click();
  await expect(activePage(page).getByRole("heading", { name: "Actor Library" })).toBeVisible();

  await page.getByLabel("Missing-image only").check();
  await page.getByRole("button", { name: "Filter actors" }).click();
  const actorsTable = page.getByRole("table", { name: "Actors" });
  await expect(actorsTable).toContainText("Aiko Fixture");
  await expect(actorsTable).not.toContainText("Mina Complete");
  await expect(page.getByLabel("Aiko Fixture portrait missing")).toBeVisible();

  const actorRow = page.getByRole("row", { name: /Aiko Fixture/ });
  await actorRow.getByLabel("Aliases for Aiko Fixture").fill("A. Fixture\nAiko Test Alias");
  await actorRow.getByRole("button", { name: "Save aliases" }).click();
  await expect(page.getByText("Aliases saved for Aiko Fixture")).toBeVisible();
  await expect(actorRow.getByLabel("Aliases for Aiko Fixture")).toHaveValue(
    "A. Fixture\nAiko Test Alias",
  );

  await page.getByLabel("Replacement portrait file").setInputFiles({
    name: "portrait-fixture.png",
    mimeType: "image/png",
    buffer: Buffer.from("synthetic portrait fixture bytes"),
  });
  await actorRow.getByRole("button", { name: "Replace image" }).click();
  await expect(page.getByText("Portrait replaced (32 bytes)")).toBeVisible();

  await actorRow.getByRole("button", { name: "Sync Emby" }).click();
  await expect(page.getByText(/Emby sync uploaded portrait/)).toBeVisible();
  await expect(page.getByText("emby-secret-key")).toHaveCount(0);
  await expect(actorRow).toContainText("emby-person-1");
  await expectNoOverlappingControls(page);
});

function activePage(page: Page) {
  return page.locator(".page-header");
}

async function resetFixture(request: APIRequestContext) {
  const response = await request.post(`${backendURL}/api/e2e/reset`);
  expect(response.ok()).toBeTruthy();
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
