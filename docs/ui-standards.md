# Xona UI Standards

本文档是 Xona 项目的 UI 规范。后续新增功能、页面或表单时，只要涉及前端 UI，都应遵循这里的标准，避免页面风格再次变得粗糙、不统一。

## 设计目标

Xona 的 UI 应该像一个现代本地控制台，而不是临时拼出来的后台表单。

关键词：

- **现代**：圆角、留白、柔和阴影、清晰层级。
- **稳重**：偏工具/控制台气质，使用中性浅色、低饱和状态色，不做花哨娱乐化风格。
- **一致**：按钮、输入框、卡片、tab、表格、弹窗都使用统一尺寸和视觉语言。
- **可解释**：用户不应该靠猜。路径、URL、模板、规则等字段必须有说明、placeholder 或可选辅助面板。
- **本地优先**：UI 文案要体现本地整理、安全门禁、预览执行、可回滚这些核心概念。

## 页面结构

### 一级导航

- 左侧固定竖向菜单用于一级模块导航。
- 一级模块包括：仪表盘、手动整理、自动监控、复核队列、任务中心、演员库、历史/回滚、设置。
- 左侧菜单项应包含 icon、label、hover 状态、当前页高亮。
- 不要在内容区重复做一级菜单。

### 二级 Tab

当一个一级页面内部有多个明显分区时，右侧内容区顶部使用横向 tab。

适合使用 tab 的情况：

- 设置页：XChina、Emby、存储根、命名模板、元数据/资源、置信度/安全、认证。
- 手动整理页：浏览/扫描、搜索/复核/预览执行。
- 自动监控页：监控规则、任务队列。
- 演员库：列表、同步。

Tab 规范：

- 使用 `Tabs` 组件。
- 外层使用浅灰 segmented pill。
- active tab 使用白底或浅灰底、深灰描边和 pill 状态，不使用强色填充。
- hover 使用浅灰底和更清楚的灰边框。
- tab bar 应横向排列，可横向滚动。
- tab 切换只影响当前页面内部分区，不改变一级导航状态。

### 工作流页面

涉及明确流程的页面，不应只是把大量表单平铺出来。应使用工作流式布局，让用户知道当前在哪一步、下一步做什么。

手动整理页标准流程：

1. **扫描**：选择源目录、设置递归和忽略模式、生成任务。
2. **匹配/复核**：选择任务、搜索候选项、确认详情 URL 和安全门禁。
3. **预览/执行**：选择目标目录、整理模式、命名模板，先生成预览再执行。

要求：

- 顶部使用 `.workflow-progress` 展示步骤。
- 当前步骤使用 active 状态，已完成步骤使用 complete 状态。
- 每一步都应有一个主要 CTA，不要让多个同级按钮抢焦点；同一 section 最多一个主要 CTA。
- 扫描成功后可以自动进入匹配/复核；候选项接受后可以自动进入预览/执行。
- 路径字段必须接 `DirectoryPicker`，不要暴露 root id 这类实现细节给用户。

## 布局和层级

### 内容容器

- 页面主体使用 `.page-stack`。
- 功能块使用 `Section` / `.section` 卡片。
- section 内部优先使用 grid：`.grid.two`、`.grid.three`、`.grid.four`。
- 不要把大量无边界控件直接堆在白底页面上。

### Dashboard

Dashboard 是产品第一眼，应保持控制台质感：

- 顶部使用 `hero-panel`，说明当前系统定位和状态。
- 指标使用 `.metric` 卡片，而不是普通文字。
- 流程使用 `.workflow-step`，表现扫描 → 搜索 → 复核 → 预览 → 执行 → 回滚。
- 空数据状态显示 `-`，并配简短说明。

## 表单规范

### 基础要求

- 所有表单项使用 `FormField` 或 `CheckboxField`。
- 不直接裸放 label + input，避免对齐和间距失控。
- 输入框、按钮、select、textarea 必须保持统一高度、圆角和 focus 状态。
- 混排按钮和输入框时使用 `.path-field`、`.button-row` 或 `.button-column`，不要随意 inline。

### Placeholder

凡是用户可能不知道格式的输入项，必须提供灰色 placeholder 示例。

示例：

- URL：`http://emby:8096`
- FlareSolverr：`http://solver:8191/v1`
- 代理：`http://user:***@127.0.0.1:7890`
- 路径：`/downloads`、`/media/jav`
- 命名模板：`{xchina_id} - {title}`
- 多行模板：`{studio}\n{title}`
- include pattern：`*.mkv\n*.mp4`
- exclude pattern：`*.sample.*\n@eaDir/**`

规则：

- placeholder 只作为示例，不应作为实际默认值提交。
- 敏感字段示例必须脱敏，不出现真实 key、真实代理密码、真实 Cookie。
- 不要给无实际用途的字段添加误导性 placeholder；无价值字段应隐藏。

### 路径选择

涉及目录路径的字段，不应只靠手写。

必须：

- 提供 `DirectoryPicker` 入口。
- 允许选择存储根。
- 允许点击目录逐层进入。
- 支持“上一层”“刷新”“选择当前目录”。
- 环境变量来源的 storage root 标记为只读，不允许保存时覆盖。

适用字段：

- 存储根。
- XChina 缓存目录。
- Emby 容器根目录 / 可见根目录。
- 其他需要选择本地目录的新增字段。

例外：

- 如果字段当前没有实际业务用途，应隐藏，不要暴露给用户。

## 命名模板规范

命名模板页面必须告诉用户可用变量。

要求：

- 文件夹模板和文件名模板都必须支持变量插入。
- 使用“查看可用变量”面板。
- 变量按钮点击后插入到当前聚焦输入框。
- 变量说明必须清楚，例如：
  - `{number}`：番号或作品编号
  - `{title}`：作品标题
  - `{studio}`：制作商
  - `{actors}`：演员列表
  - `{first_actor}`：第一位演员
  - `{source_filename}`：源文件名
  - `{xchina_id}`：XChina 作品 ID

新增模板变量时必须同步更新 UI 变量面板和后端模板测试。

## 视觉风格

### 色彩

使用 `frontend/src/styles.css` 中的 CSS variables：

- `--bg`：页面背景。
- `--panel`：卡片背景。
- `--panel-soft`：弱背景。
- `--text`：正文。
- `--muted`：说明文字。
- `--border` / `--border-strong`：边框。
- `--primary`：中性深灰主强调，用于文字、边框和少量主要动作。
- `--primary-soft`：中性浅灰选中/弱强调背景。
- `--danger`、`--success`、`--warning`：状态色。

不要在新组件里随意硬编码一套不同颜色；优先复用变量。默认 UI 语言不得是黑底白字；深色底只用于日志 console、危险确认或极少量明确 CTA。

### 按钮

按钮默认使用紧凑 pill、浅色填充、灰色边框和清楚 hover 边界。同一行按钮必须等高。

| 类型 | 高度 | 用途 |
| --- | --- | --- |
| 默认按钮 | 34-36px | 普通表单操作 |
| `.button-compact` | 30-32px | 表格行内操作、次级工具栏 |
| `.icon-button` | 30-32px 正方形 | 关闭、刷新、返回、展开 |
| `.primary` | 36px 以内 | 每个主要区域唯一主操作 |
| `.secondary` | 34-36px | 普通次要操作 |
| `.ghost` | 32-34px | 低优先级操作 |
| `.danger-button` | 34-36px | 删除、回滚、执行高风险动作 |

规则：

- 图标统一 15-16px，只有页面主体插图可更大。
- 表格行内按钮必须 compact，不使用大 CTA。
- 文案按钮优先短动作词，例如“扫描”“预览”“执行”“刷新”“重试”“查看”。
- Disabled 状态降低透明度但保持尺寸。

### 圆角和阴影

- 普通控件：pill 或 10-12px 圆角。
- 卡片/section：约 14-16px 圆角。
- Hero / 大面板：约 16px 圆角。
- 弹窗：约 18px 圆角。
- 阴影要柔和，不要厚重黑影。

### 文案层级

- 页面标题使用 page header。
- section 内标题用 `Section`。
- section 内需要额外说明时用 `.section-heading` + `.eyebrow`。
- 技术说明放在 `description` / `.field-help`，不要塞到 label 里。

## 交互状态

每个可交互元素都应有明确状态：

- hover。
- disabled。
- active / selected。
- focus。

表单 focus 必须有可见描边/光晕，方便键盘操作。active / selected 状态优先使用 pill、浅灰底和深灰描边。

## 弹窗和浏览器

弹窗使用：

- `.dialog-backdrop`
- `.dialog`
- 具体弹窗类，例如 `.directory-picker-dialog`

要求：

- backdrop 有半透明遮罩和轻微 blur。
- 弹窗最大高度不超过视口，内容可滚动。
- 右上或顶部明确有关闭按钮。
- 关键路径/当前目录使用 `code` 样式展示，允许长路径换行或省略。

## 数据表格

表格用于列表型数据，不用于排布表单。

要求：

- 表头使用 muted 小字号。
- 行间隔清晰。
- 移动端保持可读，必要时块状显示。
- 操作按钮集中到 `.button-row`，使用 `.button-compact` 或由表格样式压缩到 30-32px。
- 列表外层使用 `.table-wrap`，保护横向溢出。

## 队列、任务和历史页

复核队列、任务中心、历史/回滚这类运维型页面，应使用控制台式结构，不要只放一张裸表。

标准结构：

1. 顶部使用 `.metric-grid` 展示关键数量或当前状态。
2. 主操作区使用 `Section`，顶部放 `.section-toolbar` 和 `.section-lead` 说明。
3. 列表外层使用 `.table-wrap`，保持横向溢出可控。
4. 状态、校验、复核原因使用 `.status-pill`，多个原因用 `.reason-list`。
5. 未加载、空数据、无事件时使用 `.empty-state`，不要显示空白区域。
6. 任务事件使用 `JobTimeline`，payload 必须脱敏。
7. 操作历史和回滚预览使用 `OperationPlanView`，回滚拒绝要明确显示原因。

具体约定：

- 复核队列：展示待复核数量、已生成计划数量、安全门禁数量。
- 任务中心：展示当前任务、任务状态、时间线事件数量；未加载任务时按钮应按状态禁用。
- 历史/回滚：展示历史计划、完成记录、外部变更数量；回滚前后的状态必须明确。
- API 返回异常结构时，页面不得白屏；数组字段应防御式归一化为空数组。

## 日志页

日志页用于本地排障，应作为安全默认的应用日志查看器，而不是宿主机 Docker 控制面板。

标准结构：

1. 顶部使用 `.metric-grid` 展示日志条目、警告、错误数量。
2. 主区域使用 `Section` 和 `.section-toolbar`，说明日志来源和 `docker logs` 对应关系。
3. 日志输出使用 `.log-console`，保持等宽字体、暗色背景、可滚动。
4. 日志级别使用 `.status-pill`。
5. 支持最近日志刷新、实时跟随、级别筛选、自动滚动、清屏（只清 UI，不删除服务端日志）。
6. 实时日志优先用 SSE（`EventSource`），不要用高频轮询。
7. 默认不要挂载 Docker socket，也不要读取宿主机其他容器日志；Xona 应用日志写 stdout，部署后由 `docker logs` 查看。
8. 日志、诊断和事件 payload 必须脱敏后展示。

## 错误兜底和错误提示

产品页面不能因为单个 React 渲染错误整站白屏。

标准：

1. 每个主导航页面必须由页面级 `ErrorBoundary` 包裹；出错时保留侧边栏、页头和全局安全模式开关。
2. ErrorBoundary fallback 必须使用中文友好说明，至少提供：错误摘要、重试当前页面、返回仪表盘。
3. 导航到其他页面时必须重置 ErrorBoundary，不能把旧页面错误带到新页面。
4. 非致命 API/业务错误优先使用统一 `ErrorNotice`，不要散落裸 `status error` 文本。
5. `ErrorNotice` 应包含清楚标题、可读消息，并在可恢复场景提供重试动作。
6. 技术细节可以放进折叠区域；默认不要暴露密钥、Cookie、token、代理密码或真实敏感路径。

## 安全和隐私

- UI 示例不得包含真实 API key、Cookie、代理密码、真实用户路径。
- 密钥字段默认 password 类型。
- 脱敏占位符必须保留语义，避免用户误删已有密钥。
- 图片安全模式默认开启，候选图和演员头像默认模糊。
- 诊断、时间线和 API 返回 payload 中的 `api_key`、`token`、`cookie`、`password`、`secret`、`Authorization`、代理账号密码必须脱敏后展示。

## 新增 UI 的检查清单

提交任何 UI 改动前，至少检查：

1. 是否使用现有组件：`Section`、`FormField`、`CheckboxField`、`Tabs`、`DirectoryPicker`。
2. 输入项是否有合适 placeholder 或 description。
3. 涉及目录时是否提供路径选择器。
4. 是否避免暴露无实际用途的配置项。
5. 是否复用 CSS variables，没有另起一套颜色。
6. 按钮/输入框是否对齐，高度是否一致。
7. 空数据状态是否可理解。
8. 敏感示例是否脱敏。
9. `frontend npm run build` 是否通过。
10. 核心页面是否实际截图或本地打开检查过。
11. 如果页面是流程型任务，是否使用工作流步骤表达，而不是平铺所有表单。

## 验证命令

前端改动至少运行：

```bash
cd frontend
npm run build
```

涉及设置 API / storage roots / 模板变量时，额外运行相关后端测试：

```bash
python3 -m pytest \
  tests/backend/api/test_settings_api.py \
  tests/backend/api/test_storage_roots_api.py \
  tests/backend/services/test_storage_root_source_of_truth.py \
  tests/backend/services/test_storage_roots.py \
  tests/backend/services/test_templates.py
```

如修改 Dockerfile 或容器配置，再跑对应 integration tests。
