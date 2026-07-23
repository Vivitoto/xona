import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  review_job_id: number;
  history_plan_id: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("Review Queue, Task Center, and History/Rollback use jobs/history APIs and render redacted events", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);
  const apiPaths: string[] = [];
  page.on("request", (apiRequest) => {
    const url = new URL(apiRequest.url());
    if (url.pathname.startsWith("/api/jobs") || url.pathname.startsWith("/api/history")) {
      apiPaths.push(`${url.pathname}${url.search}`);
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Review Queue" }).click();
  await expect(page.getByRole("table", { name: "Review required jobs" })).toContainText(
    "Review.Required.Work.2026",
  );
  await expect(page.getByRole("table", { name: "Review required jobs" })).toContainText(
    "confidence_below_threshold",
  );

  await page.getByRole("button", { name: "Task Center" }).click();
  await page.getByLabel("Job ID").fill(String(fixture.review_job_id));
  await page.getByRole("button", { name: "Load job" }).click();
  await expect(page.getByLabel("Job timeline")).toContainText("review_required");
  await expect(page.getByLabel("Job timeline")).toContainText("********");
  await expect(page.getByText("super-secret-token")).toHaveCount(0);
  await expect(page.getByText("emby-secret-key")).toHaveCount(0);

  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByText("Job loaded")).toBeVisible();
  await expect(page.getByLabel("Job timeline").getByText("searching")).toBeVisible();

  await page.getByRole("button", { name: "History/Rollback" }).click();
  await expect(page.getByRole("table", { name: "Operation history" })).toContainText(
    fixture.history_plan_id,
  );
  await expect(page.getByLabel("Operation plan")).toContainText("Archived Work");
  const rollbackResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/plans/${fixture.history_plan_id}/rollback`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Rollback", exact: true }).click();
  const rollbackResponse = await rollbackResponsePromise;
  expect(rollbackResponse.ok()).toBeTruthy();
  expect(await rollbackResponse.json()).toMatchObject({
    plan_id: fixture.history_plan_id,
    status: "rolled_back",
    reversed_steps: ["copy-media"],
  });

  expect(apiPaths).toContain("/api/jobs?state=review_required");
  expect(apiPaths).toContain(`/api/jobs/${fixture.review_job_id}`);
  expect(apiPaths).toContain(`/api/jobs/${fixture.review_job_id}/events`);
  expect(apiPaths).toContain("/api/history/plans");
  await expectNoOverlappingControls(page);
});

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
