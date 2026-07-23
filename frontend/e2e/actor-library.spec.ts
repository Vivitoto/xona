import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("演员库 filters missing images, edits aliases, uploads portrait bytes, and syncs Emby", async ({
  page,
  request,
}) => {
  await resetFixture(request);

  await page.goto("/");
  await page.getByRole("button", { name: "演员库" }).click();
  await expect(activePage(page).getByRole("heading", { name: "演员库" })).toBeVisible();

  await page.getByLabel("仅缺少图片").check();
  await page.getByRole("button", { name: "筛选演员" }).click();
  const actorsTable = page.getByRole("table", { name: "演员" });
  await expect(actorsTable).toContainText("Aiko Fixture");
  await expect(actorsTable).not.toContainText("Mina Complete");
  await expect(page.getByLabel("Aiko Fixture 缺少头像")).toBeVisible();

  const actorRow = page.getByRole("row", { name: /Aiko Fixture/ });
  await actorRow.getByLabel("Aiko Fixture 的别名").fill("A. Fixture\nAiko Test Alias");
  await actorRow.getByRole("button", { name: "保存别名" }).click();
  await expect(page.getByText("已保存 Aiko Fixture 的别名")).toBeVisible();
  await expect(actorRow.getByLabel("Aiko Fixture 的别名")).toHaveValue(
    "A. Fixture\nAiko Test Alias",
  );

  await page.getByLabel("替换头像文件").setInputFiles({
    name: "portrait-fixture.png",
    mimeType: "image/png",
    buffer: Buffer.from("synthetic portrait fixture bytes"),
  });
  await actorRow.getByRole("button", { name: "替换图片" }).click();
  await expect(page.getByText("头像已替换（32 字节）")).toBeVisible();

  await actorRow.getByRole("button", { name: "同步 Emby" }).click();
  await expect(page.getByText(/Emby 同步已上传头像/)).toBeVisible();
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
