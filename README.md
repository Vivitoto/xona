# Xona

Xona 是一个本地优先的媒体元数据与整理工作台。它面向已经挂载到容器/NAS/家庭服务器的视频文件，支持本地分析视频、生成截图、自动产出 Emby/Jellyfin 兼容的 NFO 与封面资源，并在用户确认后按计划复制、移动、硬链接或软链接媒体文件。

XChina 搜索现在是辅助元数据来源之一；Xona 也可以只依赖本地视频路径和用户编辑内容完成整理。它适合部署在 NAS、家庭服务器或 Docker 主机上，配合 Emby/Jellyfin 这类媒体库使用。

## 主要功能

- **本地元数据生成**：分析本地视频、清理标题、编辑元数据、生成 NFO 预览。
- **本地封面资源**：自动抽取截图并默认选择前 9 张，生成 `poster.jpg`、`fanart.jpg`、`thumb.jpg` 和可选 backdrop 背景图。
- **XChina 元数据搜索**：独立搜索 XChina 来源、查看详情、复制来源链接，并可作为本地元数据的补充来源。
- **整理计划预览**：基于命名模板生成目标路径，预览 NFO、封面和文件操作后再执行。
- **批量草稿**：扫描目录后为多个视频生成可编辑草稿，再逐个确认整理计划。
- **任务中心**：查看任务状态、时间线，支持重试/取消。
- **历史/回滚**：查看已执行计划，必要时执行回滚。
- **演员库**：缓存演员信息和头像，可同步到 Emby。
- **设置中心**：管理媒体目录、命名模板、整理默认值、XChina、Emby 与图片安全模式。
- **日志页面**：在 Web UI 中查看最近日志，也可用 `docker logs` 查看。

## Docker 部署

### 1. 准备目录

在宿主机准备两个目录：

```bash
mkdir -p ./config ./media
```

- `./config`：保存 Xona 配置、数据库、缓存等数据。
- `./media`：示例媒体目录；实际使用时可以换成你的下载目录或媒体库目录。

### 2. 创建 `docker-compose.yml`

```yaml
services:
  xona:
    image: vivitoto/xona:latest
    container_name: xona
    ports:
      - "8732:8732"
    environment:
      PUID: "1000"
      PGID: "1000"
    volumes:
      - "./config:/config"
      - "./media:/media"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "/usr/local/bin/xona-healthcheck.py"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
```

如果你的媒体目录在别的位置，例如 `/mnt/downloads`，把 volume 改成：

```yaml
      - "/mnt/downloads:/media"
```

如果想保留容器内路径名，也可以直接挂成任意路径：

```yaml
      - "/mnt/downloads:/downloads"
      - "/mnt/archive:/archive"
```

Xona 会在容器启动时自动发现这些挂载目录，并在 **设置 → 媒体目录** 中显示。没有发现任何媒体挂载目录时，容器日志会提示需要挂载媒体目录。

### 3. 启动

```bash
docker compose up -d
```

访问：

```text
http://localhost:8732
```

查看日志：

```bash
docker logs -f xona
```

日志格式为 `时间 | 级别 | 组件 | 信息`，例如 `app`、`service.worker`、`api.manual`。默认不输出健康检查和静态资源访问日志；需要更详细日志时可在 `.env` 中设置 `LOG_LEVEL=DEBUG`。

停止：

```bash
docker compose down
```

## 使用说明

### 初次设置

1. 打开 Web UI：`http://localhost:8732`
2. 进入 **设置 → 媒体目录**，确认容器挂载目录已经自动显示。
3. 进入 **设置 → XChina**，按需要配置：
   - XChina 地址
   - FlareSolverr 地址
   - 代理 URL
   - 缓存目录
4. 如果需要同步媒体库，进入 **设置 → Emby**，填写 Emby 地址和 API key。
5. 进入 **设置 → 命名模板**，确认目录和文件命名规则。

### 本地元数据整理流程

1. 进入 **本地元数据生成**。
2. 在“视频路径”选择或填写已挂载媒体目录下的视频文件，点击 **分析并生成截图**。
3. Xona 会分析视频技术信息、生成默认标题/整理文件名，并自动选择前 9 张截图作为 Poster/Fanart/Thumb 素材；你也可以手动调整截图选择或重新自动选择前 9 张。
4. 按需要编辑标题、封面文字、演员、简介、标签、类型、封面模板、字体与文字位置。
5. 点击 **生成封面预览**，确认 `poster.jpg`、`fanart.jpg`、`thumb.jpg` 效果。
6. 填写目标目录、整理模式、文件夹模板、文件名模板，以及可选的额外 backdrop 数量。
7. 点击 **生成整理预览**，确认 NFO、封面资源和文件操作计划。
8. 确认无误后点击 **按当前预览执行整理**。

如果希望参考站点元数据，可以进入 **XChina 元数据搜索**，搜索关键词或粘贴详情 URL，查看详情后复制/套用来源信息。

### 命名模板

文件夹模板支持多行：**一行代表一级目录**。

例如想生成：

```text
/media/Studio/XC-001 - Sample Title/XC-001 - Sample Title.mkv
```

可以这样填写：

**文件夹模板**

```text
{studio}
{xchina_id} - {title}
```

**文件名模板**

```text
{xchina_id} - {title}
```

常用变量：

- `{xchina_id}`：XChina ID
- `{number}`：番号/作品编号
- `{title}`：作品标题
- `{original_title}`：原始标题
- `{studio}`：制作商
- `{series}`：系列
- `{year}`：年份
- `{release_date}`：发布日期
- `{actors}`：演员列表
- `{first_actor}`：第一位演员
- `{source_filename}`：源文件名

不要在单行模板里用 `/` 写多级目录；如果需要多级目录，请把每一级拆成多行。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PUID` | `1000` | 容器内进程使用的用户 ID。 |
| `PGID` | `1000` | 容器内进程使用的用户组 ID。 |
| `CONFIG_DIR` | `/config` | 配置和数据库目录，通常无需修改。 |

大多数集成配置都可以在 Web UI 的设置页里填写。
