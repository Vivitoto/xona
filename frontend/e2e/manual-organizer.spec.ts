import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  destination_dir: string;
  sample_file: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("本地元数据生成 analyzes a local video, previews assets, and executes a copy plan", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);

  await page.goto("/");
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "本地元数据生成" })
    .click();
  await expect(activePage(page).getByRole("heading", { name: "本地元数据生成" })).toBeVisible();

  await page.getByLabel("视频路径").fill(fixture.sample_file);
  await page.getByRole("button", { name: "分析并生成截图" }).click();
  await expect(page.getByText("分析完成，已生成 9 张截图")).toBeVisible();
  await expect(page.getByLabel("标题 (title)")).toHaveValue("Sample Work Alpha 2026");
  await expect(page.locator(".frame-thumb")).toHaveCount(9);

  await page.getByLabel("标题 (title)").fill("Local Fixture Title");
  await page.getByLabel("整理文件名 (organize_filename)").fill("Local Fixture Output");
  await page.getByLabel("演员 (actor)").fill("Aiko Fixture\nActor One");
  await page.getByRole("button", { name: "生成封面预览" }).click();
  await expect(page.getByAltText("Poster preview")).toBeVisible();

  await page.getByRole("button", { name: "生成 NFO 预览" }).click();
  await expect(page.locator(".nfo-preview")).toContainText("Local Fixture Title");

  const organizePreview = page.locator("section.section", {
    has: page.getByRole("heading", { name: "整理预览" }),
  });
  await organizePreview.getByLabel("目标目录", { exact: true }).fill(fixture.destination_dir);
  await organizePreview.getByLabel(/^模式/).selectOption("copy");
  await page.getByRole("button", { name: "生成整理预览" }).click();
  await expect(page.getByLabel("整理输出概要")).toContainText("Local Fixture Output.mkv");
  await expect(page.getByLabel("整理输出概要")).toContainText("Local Fixture Output.nfo");

  await page.getByRole("button", { name: "按当前预览执行整理" }).click();
  await expect(page.getByText(/计划 fixture-local-plan-\d+：整理完成/)).toBeVisible();
  await expectNoOverlappingControls(page);
});

test("本地元数据生成 controls remain readable at a narrow desktop width", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);
  await page.setViewportSize({ width: 1100, height: 900 });

  await page.goto("/");
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "本地元数据生成" })
    .click();
  await page.getByLabel("视频路径").fill(fixture.sample_file);
  await page.getByRole("button", { name: "分析并生成截图" }).click();
  await expect(page.getByText("分析完成，已生成 9 张截图")).toBeVisible();

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
