# Xona

Xona 是一个本地优先的 Docker Web 应用，用于扫描挂载的媒体目录、搜索并整理 xchina 元数据、预览安全的文件操作计划、写入 Emby 兼容的元数据/图片，并保留可回滚的操作记录。

## 功能概览

- 本地 Web UI：手动整理、自动监控、复核队列、任务中心、演员库、历史/回滚、设置。
- 中文为主的界面；必要技术名词保留英文，例如 Xona、Emby、XChina、FlareSolverr、URL、API key。
- 图片安全模式默认开启：候选图片和演员头像默认模糊，可在页面顶部关闭。
- 配置保存在 `/config`，媒体目录通过 Docker volume 挂载。
- 支持 Web 设置页配置 XChina、FlareSolverr、代理、Emby、命名模板、元数据策略、认证等。
- 默认发布/测试流程不访问真实 xchina，不触碰用户媒体。

## 镜像

发布后可使用以下镜像：

```bash
vivitoto/xona:1.0.0
vivitoto/xona:latest
ghcr.io/vivitoto/xona:1.0.0
ghcr.io/vivitoto/xona:latest
```

> 注意：当前仓库发布前不要把真实 API key、Cookie、代理账号密码、Emby key 或用户媒体路径提交到 GitHub。

## Docker Compose 示例

推荐先使用本地 `./config` 和一个明确的媒体目录。下面示例已脱敏，请把 `/path/to/your/media` 替换成你的实际媒体路径。

```yaml
services:
  xona:
    image: vivitoto/xona:1.0.0
    container_name: xona
    ports:
      - "8732:8732"
    environment:
      PUID: "1000"
      PGID: "1000"
      # 可选：启动时自动把容器内 /a 注册为媒体根目录。
      # 如果删掉这行，也可以在 Web 设置页手动添加 /a。
      STORAGE_ROOTS: /a
      # 可选：也可以通过环境变量固定集成配置；更推荐在 Web 设置页填写。
      # FLARESOLVERR_URL: "http://flaresolverr:8191/v1"
      # PROXY_URL: "http://user:REDACTED@proxy:7890"
      # EMBY_SERVER_URL: "http://emby:8096"
      # EMBY_API_KEY: "REDACTED"
    volumes:
      - "./config:/config"
      - "/path/to/your/media:/a"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "/usr/local/bin/xona-healthcheck.py"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
```

启动：

```bash
docker compose up -d
```

访问：

```text
http://localhost:8732
```

健康检查：

```bash
docker exec xona python /usr/local/bin/xona-healthcheck.py
# 或
curl http://localhost:8732/healthz
```

停止：

```bash
docker compose down
```

## 配置说明

常用环境变量：

| 变量 | 用途 |
| --- | --- |
| `PUID` / `PGID` | 容器内进程使用的 UID/GID，默认 `1000`。 |
| `STORAGE_ROOTS` | 启动时注册的容器内媒体根目录，例如 `/a`。 |
| `CONFIG_DIR` | 容器内配置目录，镜像默认已是 `/config`，通常不需要写。 |
| `DATABASE_URL` | 可选数据库 URL 覆盖。默认使用 `/config` 下的本地数据库。 |
| `FLARESOLVERR_URL` | 可选 FlareSolverr endpoint，例如 `http://flaresolverr:8191/v1`。 |
| `PROXY_URL` | 可选代理 URL。不要把真实账号密码提交到仓库。 |
| `EMBY_SERVER_URL` / `EMBY_API_KEY` | 可选 Emby 集成配置。不要提交真实 API key。 |

优先建议：

- 媒体目录通过 compose volume 挂载。
- XChina、FlareSolverr、代理、Emby 等尽量在 Web 设置页填写。
- 如果环境变量和 Web 设置都存在，环境变量可能作为运行时覆盖项，适合固定部署配置。

## 本地开发

安装后端测试工具和前端依赖：

```bash
python3 -m pip install -e ".[test]"
cd frontend && npm install
```

运行前端验证：

```bash
cd frontend
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

运行后端/集成验证：

```bash
python3 -m pytest tests/backend tests/integration
python3 -m ruff check backend tests
python3 -m mypy backend/app
```

## 本地 Docker 构建

```bash
docker compose build app
docker compose up -d
python docker/healthcheck.py
docker compose exec -T app python -m backend.app.db.migrations
docker compose down
```

Compose service 名为 `app`；如需在容器内运行迁移：

```bash
docker compose exec -T app python -m backend.app.db.migrations
```

## 发布前 Gate

本地发布前推荐运行：

```bash
bash scripts/release_gate.sh
```

该脚本会 fail-fast，包含输出脱敏、Compose 清理 trap，并执行后端测试、集成测试、前端测试/构建、Playwright、Docker Compose build/up、容器健康检查、容器内迁移幂等检查、synthetic disposable media smoke、fixture 隐私检查等。默认不会 push, publish, upload，也不会运行真实 xchina smoke。

如果 Playwright 需要系统浏览器，可设置：

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/path/to/chromium bash scripts/release_gate.sh
```

也可以使用 `XONA_PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/path/to/chromium`；当 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` 未设置时，release gate 会自动映射这个变量。

## 真实 XChina smoke

`scripts/real_xchina_smoke.py` 是独立、可选、只读的真实站点 smoke，不属于默认 release gate；它是明确的 opt-in 检查。

This real smoke is opt-in, read-only, not part of default release gates, and must not touch user media.

只有在明确需要时才运行，并且必须使用一次性目录：

```bash
XONA_REAL_XCHINA_SMOKE=1 \
XONA_REAL_XCHINA_FLARESOLVERR_URL="http://flaresolverr:8191/v1" \
XONA_REAL_XCHINA_QUERY="sample" \
python3 scripts/real_xchina_smoke.py
```

不要在提交文件中保存真实 Cookie、账号、密码、代理凭证、API key 或真实用户媒体路径。

## GitHub Actions 发布

仓库包含 Docker 发布 workflow。推送 `v1.0.0` 这类 tag 后，GitHub Actions 会构建并发布：

- `vivitoto/xona:1.0.0`
- `vivitoto/xona:latest`
- `ghcr.io/vivitoto/xona:1.0.0`
- `ghcr.io/vivitoto/xona:latest`

需要仓库配置 Docker Hub secrets：

- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`

GHCR 使用 GitHub Actions 自带的 `GITHUB_TOKEN`。
