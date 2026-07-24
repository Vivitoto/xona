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

test("设置 saves exact connector, mapping, template, threshold, and asset policy values", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);
  const flareSolverrEndpoint = "http://solver.fixture.local:8191/custom/v1?exact=1";
  const proxyURL = "socks5://proxy.fixture.local:9050";

  await page.goto("/");
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置" }).click();
  await expect(activePage(page).getByRole("heading", { name: "设置" })).toBeVisible();

  await page.getByRole("tab", { name: "媒体目录" }).click();
  await page.getByRole("textbox", { name: /媒体目录/ }).fill(fixture.media_root);
  await page.getByRole("tab", { name: "XChina" }).click();
  await page.getByLabel("精确 FlareSolverr 端点").fill(flareSolverrEndpoint);
  await page.getByLabel("代理 URL").fill(proxyURL);
  await page.getByLabel("XChina 缓存目录").fill(fixture.xchina_cache_dir);
  await page.getByRole("tab", { name: "Emby" }).click();
  await page.getByLabel("启用 Emby 通知").check();
  await page.getByLabel("Emby 服务器 URL").fill("http://emby.fixture.local:8096");
  await page.getByLabel("Emby API key").fill("emby-fixture-key");
  await page.getByRole("button", { name: "添加映射" }).click();
  await page.getByLabel("容器根目录").fill(fixture.media_root);
  await page.getByLabel("Emby 可见根目录").fill("/emby/fixture-media");
  await page.getByRole("tab", { name: "命名模板" }).click();
  await page.getByLabel("文件夹模板").fill("{studio}\n{series}\n{title}");
  await page.getByLabel("文件名模板").fill("{xchina_id} - {title} [{release_date}]");
  await page.getByRole("tab", { name: "元数据/资源" }).click();
  await page.getByLabel("资源策略").selectOption("strict");
  await page.getByRole("tab", { name: "置信度/安全" }).click();
  await page.getByLabel("置信度阈值").fill("87");
  await page.getByLabel("安全缓存目录").fill(fixture.safety_cache_dir);
  await page.getByRole("button", { name: "保存设置" }).click();

  await expect(page.getByText("设置已保存")).toBeVisible();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "仪表盘" }).click();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "设置" }).click();

  await page.getByRole("tab", { name: "XChina" }).click();
  await expect(page.getByLabel("精确 FlareSolverr 端点")).toHaveValue(
    flareSolverrEndpoint,
  );
  await expect(page.getByLabel("代理 URL")).toHaveValue(proxyURL);
  await page.getByRole("tab", { name: "Emby" }).click();
  await expect(page.getByLabel("容器根目录")).toHaveValue(fixture.media_root);
  await expect(page.getByLabel("Emby 可见根目录")).toHaveValue("/emby/fixture-media");
  await page.getByRole("tab", { name: "命名模板" }).click();
  await expect(page.getByLabel("文件夹模板")).toHaveValue(
    "{studio}\n{series}\n{title}",
  );
  await expect(page.getByLabel("文件名模板")).toHaveValue(
    "{xchina_id} - {title} [{release_date}]",
  );
  await page.getByRole("tab", { name: "元数据/资源" }).click();
  await expect(page.getByLabel("资源策略")).toHaveValue("strict");
  await page.getByRole("tab", { name: "置信度/安全" }).click();
  await expect(page.getByLabel("置信度阈值")).toHaveValue("87");
  await expectNoClippedCriticalText(page);
});

test("自动监控 creates a rule, excludes nested destinations, scans now, and shows review-required items", async ({
  page,
  request,
}) => {
  const fixture = await resetFixture(request);

  await page.goto("/");
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "自动监控" }).click();
  await expect(activePage(page).getByRole("heading", { name: "自动监控" })).toBeVisible();

  await page.getByLabel("源目录").fill(fixture.source_dir);
  await page.getByLabel("目标目录").fill(fixture.nested_destination_dir);
  await expect(
    page.getByText(/目标目录位于被监控源目录内/),
  ).toBeVisible();
  await expect(page.getByLabel("已排除目标前缀")).toHaveValue(
    fixture.nested_destination_dir,
  );

  await page.getByLabel("置信度阈值").fill("88");
  await page.getByLabel("资源策略").selectOption("strict");
  await page.getByRole("button", { name: "创建监控规则" }).click();
  await expect(page.getByText("监控规则 rule-1 已保存")).toBeVisible();
  await expect(page.getByRole("table", { name: "自动监控规则" })).toContainText(
    fixture.nested_destination_dir,
  );

  await page.getByRole("button", { name: "立即扫描" }).click();
  await expect(page.getByText(/已为 rule-1 加入扫描队列：/)).toBeVisible();
  await expect(
    page.getByRole("table", { name: "监控器需复核任务" }),
  ).toContainText("Monitor review item");
  await expect(
    page.getByRole("table", { name: "监控器需复核任务" }),
  ).toContainText("strict_assets_missing");
  await expectNoOverlappingControls(page);
});

test("critical controls remain readable on current viewport", async ({ page, request }) => {
  await resetFixture(request);
  await page.goto("/");

  for (const name of [
    "仪表盘",
    "手动整理",
    "自动监控",
    "复核队列",
    "任务中心",
    "演员库",
    "历史/回滚",
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
