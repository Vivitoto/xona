import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  source_dir: string;
  destination_dir: string;
  sample_file: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("手动整理 scans, searches, previews assets, and executes preview/copy modes", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);

  await page.goto("/");
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "手动整理" }).click();
  await expect(activePage(page).getByRole("heading", { name: "手动整理" })).toBeVisible();

  await page.getByLabel("源目录").fill(fixture.source_dir);
  await page.getByRole("button", { name: "扫描源目录" }).click();
  await expect(page.getByText("已扫描 1 个视频文件")).toBeVisible();
  await expect(page.getByLabel("扫描到的视频文件")).toContainText("Sample.Work.Alpha.2026.mkv");

  await page.getByLabel("搜索关键词").fill("Sample.Work.Alpha.2026.mkv");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText("找到 2 个候选结果")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sample Work Alpha" })).toBeVisible();
  const firstCandidate = page.locator(".candidate-card", { hasText: "Sample Work Alpha" }).first();
  await expect(firstCandidate.getByLabel("评分明细")).toContainText("title: 60");
  await expect(firstCandidate.getByLabel("评分明细")).toContainText("actors: 20");

  await page.getByRole("button", { name: "选择候选项" }).first().click();
  await expect(page.getByText("已选择候选结果，可以预览整理计划")).toBeVisible();

  await page.getByLabel("目标目录").fill(fixture.destination_dir);
  await page.getByLabel("整理模式").selectOption("preview");
  await page.getByRole("button", { name: "预览整理计划" }).click();
  await expect(page.getByLabel("操作计划")).toContainText("模式 preview");
  await expect(page.getByLabel("操作计划")).toContainText("已缓存资源");
  await expect(page.getByLabel("操作计划")).toContainText("poster.png");

  await page.getByRole("button", { name: "执行已批准预览" }).click();
  await expect(page.getByText(/计划 fixture-plan-\d+ 状态为 previewed/)).toBeVisible();

  await page.getByLabel("整理模式").selectOption("copy");
  await page.getByRole("button", { name: "预览整理计划" }).click();
  await expect(page.getByLabel("操作计划")).toContainText("模式 copy");
  await expect(page.getByLabel("操作计划")).toContainText(
    "XC-001 - Sample Work Alpha.mkv",
  );

  await page.getByRole("button", { name: "执行已批准预览" }).click();
  await expect(page.getByText(/计划 fixture-plan-\d+ 状态为 completed/)).toBeVisible();
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
