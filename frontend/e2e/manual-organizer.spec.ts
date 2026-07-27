import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  source_dir: string;
  destination_dir: string;
  sample_file: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("手动整理 scans, searches, and starts organization from one action", async ({
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
  await expect(page.getByText("已选择候选结果，可以开始整理")).toBeVisible();

  await page.getByLabel("目标目录").fill(fixture.destination_dir);
  await page.getByLabel("整理模式").selectOption("copy");
  await page.getByRole("button", { name: "开始整理" }).click();
  await expect(page.getByLabel("整理进度日志")).toContainText("规划整理");
  await expect(page.getByLabel("整理进度日志")).toContainText("安全计划完成");
  await expect(page.getByLabel("整理进度日志")).toContainText("执行整理");
  await expect(page.getByLabel("整理进度日志")).toContainText("整理完成");
  await expect(page.getByText(/计划 fixture-plan-\d+：整理完成/)).toBeVisible();
  await expectNoOverlappingControls(page);
});

test("手动整理搜索和详情 URL 控件在窄桌面宽度保持紧凑", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);
  await page.setViewportSize({ width: 1100, height: 900 });

  await page.goto("/");
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "手动整理" }).click();
  await page.getByLabel("源目录").fill(fixture.source_dir);
  await page.getByRole("button", { name: "扫描源目录" }).click();
  await expect(page.getByText("已扫描 1 个视频文件")).toBeVisible();

  await expectNoOverlappingControls(page);
  await expectManualSearchControlsStayGrouped(page);
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

async function expectManualSearchControlsStayGrouped(page: Page) {
  const layout = await page.locator(".manual-search-controls").evaluate((controls) => {
    const searchRow = controls.querySelector(".manual-search-row");
    const detailRow = controls.querySelector(".manual-detail-url");
    const candidatePanel = document.querySelector(".candidate-results-panel");
    if (!searchRow || !detailRow || !candidatePanel) {
      return { ok: false, reason: "missing controls" };
    }
    const controlsRect = controls.getBoundingClientRect();
    const searchRect = searchRow.getBoundingClientRect();
    const detailRect = detailRow.getBoundingClientRect();
    const candidateRect = candidatePanel.getBoundingClientRect();
    return {
      ok: true,
      searchToDetailGap: detailRect.top - searchRect.bottom,
      detailToCandidatesGap: candidateRect.top - detailRect.bottom,
      controlsHeight: controlsRect.height,
      controlsBottomToCandidatesGap: candidateRect.top - controlsRect.bottom,
    };
  });

  expect(layout.ok).toBe(true);
  expect(layout.searchToDetailGap).toBeLessThanOrEqual(24);
  expect(layout.detailToCandidatesGap).toBeLessThanOrEqual(96);
  expect(layout.controlsBottomToCandidatesGap).toBeLessThanOrEqual(24);
  expect(layout.controlsHeight).toBeLessThanOrEqual(360);
}
