import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface FixturePaths {
  media_root: string;
  destination_dir: string;
  xchina_cache_dir: string;
}

const backendURL = `http://127.0.0.1:${process.env.XONA_E2E_BACKEND_PORT ?? 8765}`;

test("设置 saves exact connector, mapping, template, and asset policy values", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);
  const flareSolverrEndpoint = "http://solver.fixture.local:8191/custom/v1?exact=1";
  const proxyURL = "socks5://proxy.fixture.local:9050";

  await page.goto("/");
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置" }).click();
  await expect(activePage(page).getByRole("heading", { name: "设置" })).toBeVisible();

  await page.getByRole("tab", { name: "XChina" }).click();
  await page.getByLabel("XChina 基础 URL").fill("https://xchina.fixture.test");
  await page.getByLabel("搜索页数安全上限").fill("3");
  await page.getByLabel("精确 FlareSolverr 端点").fill(flareSolverrEndpoint);
  await page.getByLabel("代理 URL").fill(proxyURL);
  await page.getByLabel("XChina 缓存目录").fill(fixture.xchina_cache_dir);
  await page.getByRole("tab", { name: "整理配置" }).click();
  await page.getByLabel("用户媒体目录").fill(fixture.media_root);
  await page.getByLabel("默认目标目录").fill(fixture.destination_dir);
  await page.getByRole("tab", { name: "Emby" }).click();
  await page.getByLabel("启用 Emby 通知").check();
  await page.getByLabel("Emby 服务器 URL").fill("http://emby.fixture.local:8096");
  await page.getByLabel("Emby API key").fill("emby-fixture-key");
  await page.getByRole("button", { name: "添加映射" }).click();
  await page.getByLabel("容器根目录").fill(fixture.media_root);
  await page.getByLabel("Emby 可见根目录").fill("/emby/fixture-media");
  await page.getByRole("tab", { name: "整理配置" }).click();
  await page
    .getByRole("textbox", { name: "文件夹模板" })
    .fill("{studio}\n{series}\n{title}");
  await page
    .getByRole("textbox", { name: "文件名模板" })
    .fill("{xchina_id} - {title} [{release_date}]");
  await page.getByRole("tab", { name: "元数据/资源" }).click();
  await page.getByLabel("资源缺失处理").selectOption("strict");
  await page.getByRole("button", { name: "保存设置" }).click();

  await expect(page.getByText("设置已保存")).toBeVisible();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "仪表盘" }).click();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置" }).click();

  await page.getByRole("tab", { name: "XChina" }).click();
  await expect(page.getByLabel("XChina 基础 URL")).toHaveValue("https://xchina.fixture.test");
  await expect(page.getByLabel("搜索页数安全上限")).toHaveValue("3");
  await expect(page.getByLabel("精确 FlareSolverr 端点")).toHaveValue(
    flareSolverrEndpoint,
  );
  await expect(page.getByLabel("代理 URL")).toHaveValue(proxyURL);
  await page.getByRole("tab", { name: "Emby" }).click();
  await expect(page.getByLabel("容器根目录")).toHaveValue(fixture.media_root);
  await expect(page.getByLabel("Emby 可见根目录")).toHaveValue("/emby/fixture-media");
  await page.getByRole("tab", { name: "整理配置" }).click();
  await expect(page.getByRole("textbox", { name: "文件夹模板" })).toHaveValue(
    "{studio}\n{series}\n{title}",
  );
  await expect(page.getByRole("textbox", { name: "文件名模板" })).toHaveValue(
    "{xchina_id} - {title} [{release_date}]",
  );
  await page.getByRole("tab", { name: "元数据/资源" }).click();
  await expect(page.getByLabel("资源缺失处理")).toHaveValue("strict");
  await expectNoClippedCriticalText(page);
});

test("XChina 元数据搜索 finds fixture sources and fetches detail metadata", async ({
  page,
  request,
}) => {
  await resetFixture(request);

  await page.goto("/");
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "XChina 元数据搜索" })
    .click();
  await expect(activePage(page).getByRole("heading", { name: "XChina 元数据搜索" })).toBeVisible();

  await page.getByLabel("搜索关键词").fill("Sample Work Alpha");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByText("找到 2 个元数据来源。")).toBeVisible();
  const firstCandidate = page.locator(".candidate-card", { hasText: "Sample Work Alpha" }).first();
  await expect(firstCandidate).toContainText("Studio One");

  await firstCandidate.getByRole("button", { name: "查看详情" }).click();
  await expect(page.getByLabel("元数据 JSON 预览")).toContainText("XC-001");
  await page.getByRole("button", { name: "应用到本地元数据生成" }).click();
  await expect(page.getByText("已暂存，可在本地元数据生成中接入。")).toBeVisible();
  await expectNoOverlappingControls(page);
});

test("critical controls remain readable on current viewport", async ({ page, request }) => {
  await resetFixture(request);
  await page.goto("/");

  for (const name of [
    "仪表盘",
    "本地元数据生成",
    "XChina 元数据搜索",
    "整理记录",
    "演员库",
    "日志",
    "设置",
  ]) {
    await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name }).click();
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
    (nodes) => {
      return nodes
        .filter((node) => {
          const rect = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          if (
            rect.width <= 0 ||
            rect.height <= 0 ||
            style.display === "none" ||
            style.visibility === "hidden"
          ) {
            return false;
          }
          if (node instanceof HTMLButtonElement) {
            return hasTextOutsideOwnBox(node, rect);
          }
          return (
            node.scrollWidth > node.clientWidth + 1 ||
            node.scrollHeight > node.clientHeight + 1
          );
        })
        .map((node) => node.textContent?.trim() || node.getAttribute("aria-label") || node.tagName)
        .slice(0, 5);

      function hasTextOutsideOwnBox(node: Element, bounds: DOMRect) {
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
        let current = walker.nextNode();
        while (current) {
          if (current.textContent?.trim()) {
            const range = document.createRange();
            range.selectNodeContents(current);
            for (const rect of Array.from(range.getClientRects())) {
              if (
                rect.width > 0 &&
                rect.height > 0 &&
                (rect.left < bounds.left - 1 ||
                  rect.right > bounds.right + 1 ||
                  rect.top < bounds.top - 1 ||
                  rect.bottom > bounds.bottom + 1)
              ) {
                range.detach();
                return true;
              }
            }
            range.detach();
          }
          current = walker.nextNode();
        }
        return false;
      }
    },
  );
  expect(clipped).toEqual([]);
}
