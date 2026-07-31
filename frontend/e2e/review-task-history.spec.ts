import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  history_plan_id: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("整理记录 lists local records, opens plan detail, and rolls back", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);
  const apiPaths: string[] = [];
  page.on("request", (apiRequest) => {
    const url = new URL(apiRequest.url());
    if (url.pathname.startsWith("/api/organize-records")) {
      apiPaths.push(`${url.pathname}${url.search}`);
    }
  });

  await page.goto("/");
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "整理记录" })
    .click();
  const recordsTable = page.getByRole("table", { name: "整理记录" });
  await expect(recordsTable).toContainText("Archived Work");
  await expect(recordsTable).toContainText("已完成");
  await expect(page.getByText("super-secret-token")).toHaveCount(0);
  await expect(page.getByText("emby-secret-key")).toHaveCount(0);

  await page.getByLabel("搜索").fill("Archived");
  await expect(recordsTable).toContainText("Archived Work");

  await page.getByRole("button", { name: "#1" }).click();
  const detailDialog = page.getByRole("dialog", { name: "整理记录详情" });
  await expect(detailDialog).toBeVisible();
  await expect(detailDialog).toContainText(fixture.history_plan_id);
  await expect(detailDialog.getByLabel("操作计划")).toContainText("Archived Work");

  const rollbackResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/organize-records/${fixture.history_plan_id}/rollback`) &&
      response.request().method() === "POST",
  );
  await detailDialog.getByRole("button", { name: "回滚", exact: true }).click();
  const rollbackResponse = await rollbackResponsePromise;
  expect(rollbackResponse.ok()).toBeTruthy();
  expect(await rollbackResponse.json()).toMatchObject({
    record_id: fixture.history_plan_id,
    plan_id: fixture.history_plan_id,
    status: "rolled_back",
    reversed_steps: [`${fixture.history_plan_id}:copy-media`],
  });
  await expect(page.getByText("回滚完成；已反转 1 个步骤")).toBeVisible();

  expect(apiPaths).toContain("/api/organize-records?limit=50");
  expect(apiPaths).toContain(`/api/organize-records/${fixture.history_plan_id}`);
  await detailDialog.getByLabel("关闭").click();
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
