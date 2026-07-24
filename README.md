# Xona

Xona 是一个本地优先的媒体整理 Web 应用，用来扫描挂载到容器里的视频目录，搜索 XChina 元数据，生成整理预览，并按确认后的计划复制、移动、硬链接或软链接媒体文件。

它适合部署在 NAS、家庭服务器或 Docker 主机上，配合 Emby/Jellyfin 这类媒体库使用。

## 主要功能

- **手动整理**：扫描目录 → 选择视频 → 搜索 XChina → 选择候选 → 预览 → 执行。
- **自动监控**：配置监控规则后，自动发现新文件并生成整理任务。
- **复核队列**：低置信度、路径冲突、资源缺失等情况会进入人工复核。
- **任务中心**：查看任务状态、时间线，支持重试/取消。
- **历史/回滚**：查看已执行计划，必要时执行回滚。
- **演员库**：缓存演员信息和头像，可同步到 Emby。
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

### 手动整理流程

1. 进入 **手动整理**。
2. 在“源目录”选择或填写已挂载媒体目录下的路径。
3. 点击 **扫描源目录**。
4. 在左侧选择扫描到的视频文件。
5. 点击 **用文件名搜索**、**用父目录搜索**，或手动填写关键词后点击 **搜索**。
6. 选择合适的 XChina 候选结果；如果搜索不到，也可以粘贴详情页 URL 后点击 **使用 URL 刮削**。
7. 在下方填写目标目录、整理模式、命名模板。
8. 点击 **预览整理计划**，确认生成路径和操作内容。
9. 确认无误后点击 **执行已批准预览**。

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