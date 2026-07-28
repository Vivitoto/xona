import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch } from "../api/client";
import type {
  AppSettings,
  CoverTemplateName,
  LocalAnalyzeResponse,
  LocalCachedAsset,
  LocalCoverPreviewRequest,
  LocalCoverPreviewResponse,
  LocalExecutePlanResponse,
  LocalFrameResponse,
  LocalMetadataDraft,
  LocalNfoPreviewResponse,
  LocalPlanPreviewRequest,
  LocalPlanPreviewResponse,
  LocalScanResponse,
  LocalScannedVideo,
  OrganizationMode,
  PosterFontId,
} from "../api/types";
import { DirectoryPicker } from "../components/DirectoryPicker";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { OperationPlanView } from "../components/OperationPlanView";
import { linesToList, listToLines, normalizeSettings } from "./settings/settingsForm";

const coverTemplates: { value: CoverTemplateName; label: string }[] = [
  { value: "simple_poster", label: "Simple Poster" },
  { value: "jav_classic_left_strip", label: "JAV Classic" },
  { value: "tangxin_vlog", label: "TangXin Vlog" },
];
const posterFonts: { value: PosterFontId; label: string }[] = [
  { value: "source_han_sans", label: "思源黑体 / Source Han Sans" },
  { value: "noto_sans_jp", label: "Noto Sans JP" },
  { value: "dela_gothic_one", label: "Dela Gothic One" },
  { value: "bebas_neue", label: "Bebas Neue" },
  { value: "anton", label: "Anton" },
  { value: "smiley_sans", label: "得意黑 / Smiley Sans" },
  { value: "zcool_qingke_huangyou", label: "站酷庆科黄油体" },
  { value: "lxgw_wenkai", label: "霞鹜文楷 / LXGW WenKai" },
];
const DEFAULT_TITLE_FONT_BY_TEMPLATE: Record<CoverTemplateName, PosterFontId> = {
  simple_poster: "source_han_sans",
  jav_classic_left_strip: "dela_gothic_one",
  tangxin_vlog: "smiley_sans",
};
const DEFAULT_TITLE_ANGLE_DEGREES = -8;
const MIN_TITLE_ANGLE_DEGREES = -20;
const MAX_TITLE_ANGLE_DEGREES = 20;
const MIN_TITLE_POSITION_PERCENT = 0;
const MAX_TITLE_POSITION_PERCENT = 100;
const DEFAULT_TITLE_POSITION_BY_TEMPLATE: Record<
  CoverTemplateName,
  { x: number; y: number }
> = {
  simple_poster: { x: 50, y: 93.41021416803954 },
  jav_classic_left_strip: { x: 87.79069767441861, y: 96.84921230307577 },
  tangxin_vlog: { x: 50, y: 90.14522821576763 },
};

type BusyAction =
  | "analyze"
  | "frames"
  | "cover"
  | "nfo"
  | "plan"
  | "execute"
  | "scan"
  | null;

interface BatchDraftStatus {
  path: string;
  filename: string;
  draft: LocalMetadataDraft;
  status: BatchDraftState;
}

type BatchDraftState = "drafted" | "loaded" | "updated";

export function UnmatchedVideosPage() {
  const [videoPath, setVideoPath] = useState("");
  const [directory, setDirectory] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [scannedVideos, setScannedVideos] = useState<LocalScannedVideo[]>([]);
  const [selectedBatchPaths, setSelectedBatchPaths] = useState<string[]>([]);
  const [draft, setDraft] = useState<LocalMetadataDraft>(() => blankDraft(""));
  const [posterTitle, setPosterTitle] = useState("");
  const [titleAngleDegrees, setTitleAngleDegrees] = useState(
    DEFAULT_TITLE_ANGLE_DEGREES,
  );
  const [titlePositionXPercent, setTitlePositionXPercent] = useState(
    DEFAULT_TITLE_POSITION_BY_TEMPLATE.simple_poster.x,
  );
  const [titlePositionYPercent, setTitlePositionYPercent] = useState(
    DEFAULT_TITLE_POSITION_BY_TEMPLATE.simple_poster.y,
  );
  const [technical, setTechnical] = useState<LocalAnalyzeResponse["technical"] | null>(
    null,
  );
  const [frames, setFrames] = useState<LocalCachedAsset[]>([]);
  const [selectedFrameIds, setSelectedFrameIds] = useState<string[]>([]);
  const [template, setTemplate] = useState<CoverTemplateName>("simple_poster");
  const [titleFontId, setTitleFontId] = useState<PosterFontId>(
    DEFAULT_TITLE_FONT_BY_TEMPLATE.simple_poster,
  );
  const [coverPreview, setCoverPreview] =
    useState<LocalCoverPreviewResponse | null>(null);
  const [nfoPreview, setNfoPreview] = useState<LocalNfoPreviewResponse | null>(null);
  const [planPreview, setPlanPreview] =
    useState<LocalPlanPreviewResponse | null>(null);
  const [executeResult, setExecuteResult] =
    useState<LocalExecutePlanResponse | null>(null);
  const [destinationRoot, setDestinationRoot] = useState("");
  const [mode, setMode] = useState<OrganizationMode>("preview");
  const [folderTemplates, setFolderTemplates] = useState("{studio}\n{title}");
  const [filenameTemplate, setFilenameTemplate] = useState("{title}");
  const [extraBackdropCount, setExtraBackdropCount] = useState(0);
  const [batchPrefix, setBatchPrefix] = useState("");
  const [batchSuffix, setBatchSuffix] = useState("");
  const [batchFilenamePrefix, setBatchFilenamePrefix] = useState("");
  const [batchFilenameSuffix, setBatchFilenameSuffix] = useState("");
  const [batchStudio, setBatchStudio] = useState("");
  const [batchSeries, setBatchSeries] = useState("");
  const [batchTags, setBatchTags] = useState(() => defaultLocalTags().join("\n"));
  const [batchGenres, setBatchGenres] = useState("");
  const [batchPlot, setBatchPlot] = useState("");
  const [batchStatuses, setBatchStatuses] = useState<BatchDraftStatus[]>([]);
  const [busy, setBusy] = useState<BusyAction>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const posterTitleTouched = useRef(false);
  const titleFontTouched = useRef(false);

  const selectedVideos = useMemo(
    () => scannedVideos.filter((video) => selectedBatchPaths.includes(video.path)),
    [scannedVideos, selectedBatchPaths],
  );
  const hasSelectedFrames = selectedFrameIds.length > 0;
  const hasLocalSource = Boolean(draft.video_path.trim() || scannedVideos.length);
  const coverDisplayTitle = posterTitle.trim() || draft.title.trim();
  const canGenerateCover =
    Boolean(draft.video_path.trim() && coverDisplayTitle && hasSelectedFrames) &&
    busy !== "cover";
  const canPreviewPlan =
    Boolean(draft.video_path.trim() && destinationRoot.trim()) && busy !== "plan";
  const canPreviewNfo =
    Boolean(draft.video_path.trim() && draft.title.trim()) && busy !== "nfo";
  const canExecutePlan =
    Boolean(planPreview && planPreview.plan.mode !== "preview" && !executeResult) &&
    busy !== "execute";

  useEffect(() => {
    let active = true;
    apiFetch<AppSettings>("/api/settings")
      .then((payload) => {
        if (!active) {
          return;
        }
        const settings = normalizeSettings(payload);
        setDestinationRoot(settings.organization_defaults.destination_directory ?? "");
        setMode(organizationModeForPreview(settings.organization_defaults.organization_mode));
        setFolderTemplates(
          listToLines(
            settings.organization_defaults.folder_templates.length
              ? settings.organization_defaults.folder_templates
              : settings.naming.folder_templates,
          ),
        );
        setFilenameTemplate(
          settings.organization_defaults.filename_template ||
            settings.naming.filename_template ||
            "{title}",
        );
      })
      .catch(() => {
        // Defaults are optional; direct local metadata generation still works.
      });
    return () => {
      active = false;
    };
  }, []);

  async function analyze(event?: FormEvent) {
    event?.preventDefault();
    if (!videoPath.trim()) {
      setError("请输入视频路径。");
      return;
    }
    setBusy("analyze");
    setError("");
    setStatus("正在分析视频");
    clearGeneratedPreviews();
    try {
      const response = await apiFetch<LocalAnalyzeResponse>(
        "/api/local-metadata/analyze",
        {
          method: "POST",
          body: { video_path: videoPath.trim() },
        },
      );
      setTechnical(response.technical);
      setVideoPath(response.video_path);
      const nextDraft = {
        ...blankDraft(response.video_path),
        title: response.cleaned_title,
        organize_filename: response.default_organize_filename,
        plot: response.default_plot,
        tags: response.default_tags,
        runtime_minutes: runtimeMinutes(response.technical.duration_seconds),
      };
      setDraft(nextDraft);
      resetPosterTitle(nextDraft.title);
      setStatus("分析完成");
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "分析失败";
      setTechnical(null);
      const fallbackTitle = titleFromPath(videoPath);
      setDraft((current) => ({
        ...current,
        video_path: videoPath.trim(),
        title: current.title || fallbackTitle,
        organize_filename: current.organize_filename || fallbackTitle,
      }));
      if (!posterTitleTouched.current && fallbackTitle) {
        setPosterTitle(fallbackTitle);
      }
      setError(message);
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function generateFrames() {
    if (!draft.video_path.trim()) {
      setError("请先输入或分析视频路径。");
      return;
    }
    setBusy("frames");
    setError("");
    setStatus("正在生成截图");
    setFrames([]);
    setSelectedFrameIds([]);
    setCoverPreview(null);
    clearPlanPreview();
    try {
      const response = await apiFetch<LocalFrameResponse>("/api/local-metadata/frames", {
        method: "POST",
        body: { video_path: draft.video_path },
      });
      setFrames(response.frames);
      setSelectedFrameIds(response.frames.slice(0, 3).map((frame) => frame.id));
      setStatus(`已生成 ${response.frames.length} 张截图`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "截图生成失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function generateCoverPreview() {
    const title = coverDisplayTitle.trim();
    if (!draft.video_path.trim() || !title) {
      setError("视频路径和封面文字不能为空。");
      return;
    }
    if (!selectedFrameIds.length) {
      setError("请先生成截图并选择至少一张截图用于封面。");
      return;
    }
    setBusy("cover");
    setError("");
    setStatus("正在生成封面");
    try {
      const body: LocalCoverPreviewRequest = {
        video_path: draft.video_path,
        title,
        title_angle_degrees: titleAngleDegrees,
        title_position_x_percent: titlePositionXPercent,
        title_position_y_percent: titlePositionYPercent,
        template,
        title_font_id: titleFontId,
        selected_frame_ids: selectedFrameIds,
      };
      const response = await apiFetch<LocalCoverPreviewResponse>(
        "/api/local-metadata/cover-preview",
        {
          method: "POST",
          body,
        },
      );
      setCoverPreview(response);
      clearPlanPreview();
      setStatus("封面预览已生成");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "封面生成失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function previewNfo() {
    if (!draft.video_path.trim() || !draft.title.trim()) {
      setError("视频路径和标题不能为空。");
      return;
    }
    setBusy("nfo");
    setError("");
    setStatus("正在生成 NFO");
    try {
      const response = await apiFetch<LocalNfoPreviewResponse>(
        "/api/local-metadata/nfo-preview",
        {
          method: "POST",
          body: { metadata: cleanedDraft(draft) },
        },
      );
      setNfoPreview(response);
      setStatus("NFO 预览已生成");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "NFO 生成失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function previewPlan() {
    if (!destinationRoot.trim()) {
      setError("请输入目标目录。");
      return;
    }
    setBusy("plan");
    setError("");
    setStatus("正在生成整理预览");
    try {
      const body: LocalPlanPreviewRequest = {
        metadata: cleanedDraft(draft),
        destination_root: destinationRoot.trim(),
        mode,
        folder_templates: linesToList(folderTemplates),
        filename_template: filenameTemplate,
        poster_ref: coverPreview?.poster.id ?? null,
        fanart_ref: coverPreview?.fanart.id ?? null,
        selected_frame_ids: selectedFrameIds,
        extra_backdrop_count: extraBackdropCount,
      };
      const response = await apiFetch<LocalPlanPreviewResponse>(
        "/api/local-metadata/preview-plan",
        {
          method: "POST",
          body,
        },
      );
      setPlanPreview(response);
      setExecuteResult(null);
      setNfoPreview({
        xml_text: response.nfo_xml,
        metadata: response.metadata,
      });
      setStatus("整理预览已生成");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "整理预览失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function executePlan() {
    if (!planPreview) {
      setError("请先生成整理预览。");
      return;
    }
    if (planPreview.plan.mode === "preview") {
      setError("当前是仅预览模式，不会执行文件整理；请选择复制、移动、硬链接或符号链接后重新生成预览。");
      return;
    }
    setBusy("execute");
    setError("");
    setExecuteResult(null);
    setStatus("正在执行整理计划");
    try {
      const response = await apiFetch<LocalExecutePlanResponse>(
        `/api/local-metadata/plans/${planPreview.plan_id}/execute`,
        {
          method: "POST",
          body: {
            approved: true,
            plan_version: planPreview.plan.version,
          },
        },
      );
      setExecuteResult(response);
      setStatus(response.state === "completed" ? "整理完成" : `整理状态：${response.state}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "整理执行失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function scanDirectory(event?: FormEvent) {
    event?.preventDefault();
    if (!directory.trim()) {
      setError("请输入目录路径。");
      return;
    }
    setBusy("scan");
    setError("");
    setStatus("正在扫描目录");
    try {
      const response = await apiFetch<LocalScanResponse>("/api/local-metadata/scan", {
        method: "POST",
        body: {
          directory: directory.trim(),
          recursive,
          ignore_patterns: [],
        },
      });
      setScannedVideos(response.videos);
      setSelectedBatchPaths(response.videos.slice(0, 5).map((video) => video.path));
      setBatchStatuses([]);
      setStatus(`已扫描 ${response.scanned_count} 个视频文件`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "目录扫描失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  function selectVideo(video: LocalScannedVideo) {
    loadDraftIntoEditor({
      ...blankDraft(video.path),
      title: video.cleaned_title,
      organize_filename: video.default_organize_filename || video.cleaned_title,
      plot: `Local metadata generated for ${video.filename}.`,
      tags: defaultLocalTags(),
    });
    setStatus(`已选择 ${video.filename}`);
  }

  function toggleBatchSelection(path: string, selected: boolean) {
    setSelectedBatchPaths((current) =>
      selected ? unique([...current, path]) : current.filter((item) => item !== path),
    );
  }

  function applyBatchFields() {
    const statuses = selectedVideos.map((video) => ({
      path: video.path,
      filename: video.filename,
      draft: buildBatchDraft(video),
      status: "drafted" as const,
    }));
    const draftToLoad =
      statuses.find((item) => item.path === draft.video_path) ??
      (!draft.video_path ? statuses[0] : null);
    setBatchStatuses(
      draftToLoad
        ? statuses.map((item) =>
            item.path === draftToLoad.path
              ? { ...item, status: "loaded" as const }
              : item,
          )
        : statuses,
    );
    if (draftToLoad) {
      loadDraftIntoEditor(draftToLoad.draft);
    }
    setStatus(`已生成 ${statuses.length} 个本地草稿`);
  }

  function buildBatchDraft(video: LocalScannedVideo): LocalMetadataDraft {
    const fallbackTitle = video.cleaned_title || titleFromPath(video.path);
    const title = `${batchPrefix}${fallbackTitle}${batchSuffix}`.trim() || fallbackTitle;
    const organizeBase =
      video.default_organize_filename || video.cleaned_title || titleFromPath(video.path);
    const organizeFilename =
      `${batchFilenamePrefix}${organizeBase}${batchFilenameSuffix}`.trim() || title;
    const tags = listFromText(batchTags);
    return cleanedDraft({
      ...blankDraft(video.path),
      title,
      organize_filename: organizeFilename,
      studio: batchStudio,
      series: batchSeries,
      plot: batchPlot.trim() || `Local metadata generated for ${video.filename}.`,
      tags: tags.length ? tags : defaultLocalTags(),
      genres: listFromText(batchGenres),
    });
  }

  function loadDraftIntoEditor(nextDraft: LocalMetadataDraft) {
    const editorDraft = cloneDraft(nextDraft);
    setVideoPath(editorDraft.video_path);
    setDraft(editorDraft);
    resetPosterTitle(editorDraft.title);
    setTechnical(null);
    clearGeneratedPreviews();
    setError("");
  }

  function loadBatchDraft(item: BatchDraftStatus) {
    loadDraftIntoEditor(item.draft);
    setBatchStatuses((current) =>
      current.map((entry) =>
        entry.path === item.path ? { ...entry, status: "loaded" } : entry,
      ),
    );
    setStatus(`已载入批量草稿：${item.filename}`);
  }

  function saveCurrentDraftToBatch(item: BatchDraftStatus) {
    const nextDraft = cleanedDraft(draft);
    if (nextDraft.video_path !== item.path) {
      setError("当前编辑器草稿与批量条目不匹配。");
      return;
    }
    setDraft(nextDraft);
    setVideoPath(nextDraft.video_path);
    setBatchStatuses((current) =>
      current.map((entry) =>
        entry.path === item.path
          ? { ...entry, draft: cloneDraft(nextDraft), status: "updated" }
          : entry,
      ),
    );
    setError("");
    setStatus(`已保存当前草稿：${item.filename}`);
  }

  function updateDraft<K extends keyof LocalMetadataDraft>(
    key: K,
    value: LocalMetadataDraft[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
    if (
      key === "title" &&
      (!posterTitleTouched.current || posterTitle === draft.title)
    ) {
      setPosterTitle(String(value));
    }
    setNfoPreview(null);
    clearPlanPreview();
    if (key === "title") {
      setCoverPreview(null);
    }
  }

  function updatePlanInput(action: () => void) {
    action();
    clearPlanPreview();
    setStatus("");
  }

  function updateTemplate(nextTemplate: CoverTemplateName) {
    const defaultPosition = DEFAULT_TITLE_POSITION_BY_TEMPLATE[nextTemplate];
    setTemplate(nextTemplate);
    setTitlePositionXPercent(defaultPosition.x);
    setTitlePositionYPercent(defaultPosition.y);
    if (!titleFontTouched.current) {
      setTitleFontId(DEFAULT_TITLE_FONT_BY_TEMPLATE[nextTemplate]);
    }
    setCoverPreview(null);
    clearPlanPreview();
  }

  function updateTitleFont(nextFontId: PosterFontId) {
    titleFontTouched.current = true;
    setTitleFontId(nextFontId);
    clearPosterDependentPreviews();
  }

  function resetPosterTitle(value: string) {
    posterTitleTouched.current = false;
    setPosterTitle(value);
  }

  function updatePosterTitle(value: string) {
    posterTitleTouched.current = true;
    setPosterTitle(value);
    clearPosterDependentPreviews();
  }

  function updateTitleAngle(value: string) {
    setTitleAngleDegrees(clampTitleAngleDegrees(value));
    clearPosterDependentPreviews();
  }

  function updateTitlePositionX(value: string) {
    setTitlePositionXPercent(clampTitlePositionPercent(value));
    clearPosterDependentPreviews();
  }

  function updateTitlePositionY(value: string) {
    setTitlePositionYPercent(clampTitlePositionPercent(value));
    clearPosterDependentPreviews();
  }

  function clearPosterDependentPreviews() {
    setCoverPreview(null);
    setNfoPreview(null);
    clearPlanPreview();
    setStatus("");
  }

  function toggleSelectedFrame(frameId: string) {
    setSelectedFrameIds((current) =>
      current.includes(frameId)
        ? current.filter((item) => item !== frameId)
        : [...current, frameId],
    );
    setCoverPreview(null);
    clearPlanPreview();
  }

  function clearPlanPreview() {
    setPlanPreview(null);
    setExecuteResult(null);
  }

  function clearGeneratedPreviews() {
    setFrames([]);
    setSelectedFrameIds([]);
    setCoverPreview(null);
    setNfoPreview(null);
    clearPlanPreview();
  }

  return (
    <div className="page-stack unmatched-workbench">
      <WorkflowProgress
        hasLocalSource={hasLocalSource}
        hasSelectedFrames={hasSelectedFrames}
        hasPlanPreview={Boolean(planPreview)}
      />

      <Section title="单个视频">
        <p className="section-lead">
          先分析单个文件或从批量扫描载入草稿，再生成截图并选择封面帧，最后预览
          NFO 与整理计划。
        </p>
        <form className="unmatched-source-grid" onSubmit={analyze}>
          <FormField label="视频路径">
            <input
              placeholder="/media/incoming/video.mp4"
              value={videoPath}
              onChange={(event) => {
                const nextPath = event.target.value;
                setVideoPath(nextPath);
                setTechnical(null);
                clearGeneratedPreviews();
                const nextDraft = draftWithUpdatedVideoPath(draft, nextPath);
                setDraft(nextDraft);
                if (
                  !posterTitleTouched.current ||
                  posterTitle === draft.title
                ) {
                  setPosterTitle(nextDraft.title);
                }
              }}
            />
          </FormField>
          <div className="field-action">
            <button disabled={busy === "analyze" || !videoPath.trim()} type="submit">
              {busy === "analyze" ? "分析中..." : "分析"}
            </button>
          </div>
          <div className="field-action">
            <button
              className="secondary"
              disabled={busy === "frames" || !draft.video_path.trim()}
              type="button"
              onClick={generateFrames}
            >
              {busy === "frames" ? "生成中..." : "生成截图"}
            </button>
          </div>
        </form>

        {technical ? <TechnicalSummary technical={technical} /> : null}
      </Section>

      <div className="unmatched-editor-layout">
        <Section title="元数据草稿">
          <div className="grid two">
            <FormField label="标题">
              <input
                value={draft.title}
                onChange={(event) => updateDraft("title", event.target.value)}
              />
            </FormField>
            <FormField
              label="整理文件名"
              description="标题写入 NFO 元数据；整理文件名用于输出视频和同名 NFO 文件。留空时使用文件名模板。"
            >
              <input
                value={draft.organize_filename ?? ""}
                onChange={(event) =>
                  updateDraft("organize_filename", event.target.value || null)
                }
              />
            </FormField>
          </div>
          <div className="grid two">
            <FormField label="封面文字">
              <textarea
                value={posterTitle}
                onChange={(event) => updatePosterTitle(event.target.value)}
              />
            </FormField>
            <FormField label="模板">
              <select
                value={template}
                onChange={(event) =>
                  updateTemplate(event.target.value as CoverTemplateName)
                }
              >
                {coverTemplates.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField
              label="封面字体"
              description="模板只提供默认字体；这里可以覆盖为任意内置字体。"
            >
              <select
                value={titleFontId}
                onChange={(event) =>
                  updateTitleFont(event.target.value as PosterFontId)
                }
              >
                {posterFonts.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </FormField>
          </div>
          <div className="grid three">
            <FormField label="文字倾斜角度">
              <input
                max={MAX_TITLE_ANGLE_DEGREES}
                min={MIN_TITLE_ANGLE_DEGREES}
                step={1}
                type="number"
                value={titleAngleDegrees}
                onChange={(event) => updateTitleAngle(event.target.value)}
              />
            </FormField>
            <FormField label="文字横向位置">
              <input
                max={MAX_TITLE_POSITION_PERCENT}
                min={MIN_TITLE_POSITION_PERCENT}
                step={1}
                type="range"
                value={titlePositionXPercent}
                onChange={(event) => updateTitlePositionX(event.target.value)}
              />
            </FormField>
            <FormField label="文字纵向位置">
              <input
                max={MAX_TITLE_POSITION_PERCENT}
                min={MIN_TITLE_POSITION_PERCENT}
                step={1}
                type="range"
                value={titlePositionYPercent}
                onChange={(event) => updateTitlePositionY(event.target.value)}
              />
            </FormField>
          </div>
          <div className="grid two">
            <FormField label="制作方">
              <input
                value={draft.studio ?? ""}
                onChange={(event) => updateDraft("studio", event.target.value || null)}
              />
            </FormField>
            <FormField label="系列">
              <input
                value={draft.series ?? ""}
                onChange={(event) => updateDraft("series", event.target.value || null)}
              />
            </FormField>
          </div>
          <FormField label="简介">
            <textarea
              value={draft.plot ?? ""}
              onChange={(event) => updateDraft("plot", event.target.value || null)}
            />
          </FormField>
          <div className="grid two">
            <FormField label="标签">
              <textarea
                value={listToLines(draft.tags)}
                onChange={(event) => updateDraft("tags", listFromText(event.target.value))}
              />
            </FormField>
            <FormField label="类型">
              <textarea
                value={listToLines(draft.genres)}
                onChange={(event) => updateDraft("genres", listFromText(event.target.value))}
              />
            </FormField>
          </div>
          <div className="button-row">
            <button
              disabled={!canGenerateCover}
              type="button"
              onClick={generateCoverPreview}
            >
              {busy === "cover" ? "生成中..." : "生成封面预览"}
            </button>
            <button
              className="secondary"
              disabled={!canPreviewNfo}
              type="button"
              onClick={previewNfo}
            >
              {busy === "nfo" ? "生成中..." : "生成 NFO 预览"}
            </button>
          </div>
        </Section>

        <Section title="截图与预览">
          <p className="section-lead">
            封面预览需要先生成截图，并至少选中一张截图作为 Poster/Fanart
            的素材。
          </p>
          {frames.length ? (
            <>
              <p className="frame-selection-status">
                已选择 {selectedFrameIds.length} 张截图用于封面和背景图。
              </p>
              <div className="frame-grid" aria-label="截图候选">
                {frames.map((frame) => {
                  const selected = selectedFrameIds.includes(frame.id);
                  return (
                    <button
                      aria-pressed={selected}
                      className={`frame-thumb${selected ? " is-selected" : ""}`}
                      key={frame.id}
                      type="button"
                      onClick={() => toggleSelectedFrame(frame.id)}
                    >
                      <img
                        alt={`截图 ${formatTime(frame.time_seconds)}`}
                        src={frame.url}
                      />
                      <span>{formatTime(frame.time_seconds)}</span>
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <strong>暂无截图</strong>
              <span>输入视频路径后生成截图，再选择至少一张用于封面。</span>
            </div>
          )}

          {coverPreview ? (
            <div className="cover-preview-grid">
              <PreviewImage asset={coverPreview.poster} label="Poster" />
              <PreviewImage asset={coverPreview.fanart} label="Fanart" />
            </div>
          ) : null}

          {nfoPreview ? (
            <div className="nfo-preview">
              <h3>NFO</h3>
              <pre>{nfoPreview.xml_text}</pre>
            </div>
          ) : null}
        </Section>
      </div>

      <Section title="整理预览">
        <div className="grid four organize-preview-grid">
          <div className="path-field">
            <FormField label="目标目录">
              <input
                placeholder="/media/organized"
                value={destinationRoot}
                onChange={(event) =>
                  updatePlanInput(() => setDestinationRoot(event.target.value))
                }
              />
            </FormField>
            <DirectoryPicker
              initialPath={destinationRoot}
              onSelect={(path) => updatePlanInput(() => setDestinationRoot(path))}
              title="选择目标目录"
            />
          </div>
          <FormField label="模式">
            <select
              value={mode}
              onChange={(event) =>
                updatePlanInput(() =>
                  setMode(event.target.value as OrganizationMode),
                )
              }
            >
              <option value="preview">仅预览</option>
              <option value="copy">复制</option>
              <option value="move">移动</option>
              <option value="hardlink">硬链接</option>
              <option value="symlink">符号链接</option>
            </select>
          </FormField>
          <FormField label="文件夹模板">
            <textarea
              value={folderTemplates}
              onChange={(event) =>
                updatePlanInput(() => setFolderTemplates(event.target.value))
              }
            />
          </FormField>
          <FormField label="文件名模板">
            <input
              value={filenameTemplate}
              onChange={(event) =>
                updatePlanInput(() => setFilenameTemplate(event.target.value))
              }
            />
          </FormField>
          <FormField
            label="额外截图数量"
            description="从已生成截图输出 Emby 兼容 backdrop1、backdrop2 等背景图；优先使用已选截图，0 表示不额外输出。"
          >
            <input
              max={10}
              min={0}
              step={1}
              type="number"
              value={extraBackdropCount}
              onChange={(event) => {
                updatePlanInput(() =>
                  setExtraBackdropCount(
                    clampExtraBackdropCount(event.target.value),
                  ),
                );
              }}
            />
          </FormField>
        </div>
        <div className="button-row organize-actions-row">
          <button
            disabled={!canPreviewPlan}
            type="button"
            onClick={previewPlan}
          >
            {busy === "plan" ? "预览中..." : "生成整理预览"}
          </button>
          <button
            className="secondary"
            disabled={!canExecutePlan}
            type="button"
            onClick={executePlan}
          >
            {executeResult
              ? "已按预览整理"
              : busy === "execute"
                ? "执行中..."
                : "按当前预览执行整理"}
          </button>
        </div>
        {planPreview?.plan.mode === "preview" ? (
          <p className="muted">当前为仅预览模式，不会写入或移动文件。</p>
        ) : null}
        {executeResult ? (
          <p className="status">
            计划 {executeResult.plan_id}：
            {executeResult.state === "completed"
              ? "整理完成"
              : `整理状态：${executeResult.state}`}
          </p>
        ) : null}
        <OperationPlanView
          plan={planPreview?.plan ?? null}
          preview={
            planPreview
              ? {
                  job_id: 0,
                  plan_id: planPreview.plan_id,
                  metadata: planPreview.metadata,
                  materialized_assets: planPreview.materialized_assets,
                  missing_assets: [],
                  plan: planPreview.plan,
                }
              : null
          }
        />
      </Section>

      <Section title="批量草稿">
        <form className="unmatched-batch-scan" onSubmit={scanDirectory}>
          <div className="path-field">
            <FormField label="目录路径">
              <input
                placeholder="/media/incoming"
                value={directory}
                onChange={(event) => setDirectory(event.target.value)}
              />
            </FormField>
            <DirectoryPicker
              initialPath={directory}
              onSelect={setDirectory}
              title="选择目录"
            />
          </div>
          <CheckboxField checked={recursive} label="递归扫描" onChange={setRecursive} />
          <div className="field-action">
            <button disabled={!directory.trim() || busy === "scan"} type="submit">
              {busy === "scan" ? "扫描中..." : "扫描目录"}
            </button>
          </div>
        </form>

        {scannedVideos.length ? (
          <div className="table-wrap">
            <table>
              <caption>未匹配视频批量列表</caption>
              <thead>
                <tr>
                  <th>选择</th>
                  <th>文件</th>
                  <th>默认标题</th>
                  <th>大小</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {scannedVideos.map((video) => (
                  <tr key={video.path}>
                    <td>
                      <input
                        aria-label={`选择 ${video.filename}`}
                        checked={selectedBatchPaths.includes(video.path)}
                        type="checkbox"
                        onChange={(event) =>
                          toggleBatchSelection(video.path, event.target.checked)
                        }
                      />
                    </td>
                    <td>{video.filename}</td>
                    <td>{video.cleaned_title}</td>
                    <td>{formatBytes(video.size_bytes)}</td>
                    <td>
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => selectVideo(video)}
                      >
                        编辑
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <strong>暂无批量条目</strong>
            <span>扫描目录后显示视频列表。</span>
          </div>
        )}

        <div className="grid three batch-draft-grid">
          <FormField label="标题前缀">
            <input
              value={batchPrefix}
              onChange={(event) => setBatchPrefix(event.target.value)}
            />
          </FormField>
          <FormField label="标题后缀">
            <input
              value={batchSuffix}
              onChange={(event) => setBatchSuffix(event.target.value)}
            />
          </FormField>
          <FormField label="整理文件名前缀">
            <input
              value={batchFilenamePrefix}
              onChange={(event) => setBatchFilenamePrefix(event.target.value)}
            />
          </FormField>
          <FormField label="整理文件名后缀">
            <input
              value={batchFilenameSuffix}
              onChange={(event) => setBatchFilenameSuffix(event.target.value)}
            />
          </FormField>
          <FormField label="制作方">
            <input
              value={batchStudio}
              onChange={(event) => setBatchStudio(event.target.value)}
            />
          </FormField>
          <FormField label="系列">
            <input
              value={batchSeries}
              onChange={(event) => setBatchSeries(event.target.value)}
            />
          </FormField>
          <FormField label="标签">
            <textarea
              value={batchTags}
              onChange={(event) => setBatchTags(event.target.value)}
            />
          </FormField>
          <FormField label="类型">
            <textarea
              value={batchGenres}
              onChange={(event) => setBatchGenres(event.target.value)}
            />
          </FormField>
          <FormField label="简介">
            <textarea
              value={batchPlot}
              onChange={(event) => setBatchPlot(event.target.value)}
            />
          </FormField>
        </div>
        <div className="button-row batch-actions-row">
          <button
            disabled={!selectedBatchPaths.length}
            type="button"
            onClick={applyBatchFields}
          >
            生成批量草稿
          </button>
        </div>

        {batchStatuses.length ? (
          <div className="table-wrap">
            <table>
              <caption>本地草稿状态</caption>
              <thead>
                <tr>
                  <th>视频</th>
                  <th>标题</th>
                  <th>整理文件名</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {batchStatuses.map((item) => {
                  const isLoadedDraft = draft.video_path === item.path;
                  return (
                    <tr
                      className={isLoadedDraft ? "is-selected-row" : undefined}
                      key={item.path}
                    >
                      <td>{item.path}</td>
                      <td>{item.draft.title}</td>
                      <td>{item.draft.organize_filename || "使用文件名模板"}</td>
                      <td>
                        <span
                          className={`status-pill ${batchStatusClass(item.status)}`}
                        >
                          {batchStatusLabel(item.status)}
                        </span>
                      </td>
                      <td>
                        <div className="button-row">
                          <button
                            className="secondary"
                            type="button"
                            aria-label={`载入批量草稿 ${item.filename}`}
                            onClick={() => loadBatchDraft(item)}
                          >
                            载入
                          </button>
                          <button
                            className="secondary"
                            disabled={!isLoadedDraft}
                            type="button"
                            aria-label={`保存当前草稿到 ${item.filename}`}
                            onClick={() => saveCurrentDraftToBatch(item)}
                          >
                            保存当前
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </Section>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? <p className="status error floating-status">{error}</p> : null}
    </div>
  );
}

function WorkflowProgress({
  hasLocalSource,
  hasSelectedFrames,
  hasPlanPreview,
}: {
  hasLocalSource: boolean;
  hasSelectedFrames: boolean;
  hasPlanPreview: boolean;
}) {
  const steps = [
    {
      number: "1",
      title: "确定来源",
      description: hasLocalSource ? "已载入本地视频草稿" : "分析文件或扫描目录",
      state: hasLocalSource ? "is-complete" : "is-active",
    },
    {
      number: "2",
      title: "选择截图",
      description: hasSelectedFrames ? "封面素材已选择" : "生成截图后选帧",
      state: hasSelectedFrames ? "is-complete" : hasLocalSource ? "is-active" : "",
    },
    {
      number: "3",
      title: "预览输出",
      description: hasPlanPreview ? "整理计划已生成" : "确认 NFO、封面和目标路径",
      state: hasPlanPreview ? "is-complete" : hasSelectedFrames ? "is-active" : "",
    },
  ];

  return (
    <section className="workflow-progress" aria-label="本地元数据流程">
      {steps.map((step) => (
        <div className={`progress-step ${step.state}`.trim()} key={step.number}>
          <b>{step.number}</b>
          <span>
            <strong>{step.title}</strong>
            <small>{step.description}</small>
          </span>
        </div>
      ))}
    </section>
  );
}

function TechnicalSummary({
  technical,
}: {
  technical: LocalAnalyzeResponse["technical"];
}) {
  return (
    <dl className="metadata-list compact">
      <div>
        <dt>时长</dt>
        <dd>{formatDuration(technical.duration_seconds)}</dd>
      </div>
      <div>
        <dt>分辨率</dt>
        <dd>
          {technical.width && technical.height
            ? `${technical.width} x ${technical.height}`
            : "未知"}
        </dd>
      </div>
      <div>
        <dt>视频编码</dt>
        <dd>{technical.video_codec ?? "未知"}</dd>
      </div>
      <div>
        <dt>音频编码</dt>
        <dd>{technical.audio_codec ?? "未知"}</dd>
      </div>
      <div>
        <dt>大小</dt>
        <dd>{formatBytes(technical.size_bytes)}</dd>
      </div>
      <div>
        <dt>FPS</dt>
        <dd>{technical.fps ? technical.fps.toFixed(2) : "未知"}</dd>
      </div>
    </dl>
  );
}

function PreviewImage({ asset, label }: { asset: LocalCachedAsset; label: string }) {
  return (
    <figure className="cover-preview">
      <img alt={`${label} preview`} src={asset.url} />
      <figcaption>
        {label} · {asset.width ?? "?"} x {asset.height ?? "?"}
      </figcaption>
    </figure>
  );
}

function blankDraft(videoPath: string): LocalMetadataDraft {
  const title = videoPath ? titleFromPath(videoPath) : "";
  return {
    video_path: videoPath,
    title,
    organize_filename: title,
    plot: null,
    tags: defaultLocalTags(),
    studio: null,
    series: null,
    release_date: null,
    runtime_minutes: null,
    genres: [],
  };
}

function cloneDraft(draft: LocalMetadataDraft): LocalMetadataDraft {
  return {
    ...draft,
    tags: [...draft.tags],
    genres: [...draft.genres],
  };
}

function cleanedDraft(draft: LocalMetadataDraft): LocalMetadataDraft {
  return {
    ...draft,
    video_path: draft.video_path.trim(),
    title: draft.title.trim() || titleFromPath(draft.video_path),
    organize_filename: draft.organize_filename?.trim() || null,
    plot: draft.plot?.trim() || null,
    studio: draft.studio?.trim() || null,
    series: draft.series?.trim() || null,
    release_date: draft.release_date?.trim() || null,
    tags: unique(draft.tags.map((tag) => tag.trim()).filter(Boolean)),
    genres: unique(draft.genres.map((genre) => genre.trim()).filter(Boolean)),
  };
}

function draftWithUpdatedVideoPath(
  draft: LocalMetadataDraft,
  nextPath: string,
): LocalMetadataDraft {
  const previousAutoTitle = titleFromPath(draft.video_path);
  const nextAutoTitle = titleFromPath(nextPath);
  const shouldRefreshTitle = !draft.title || draft.title === previousAutoTitle;
  const shouldRefreshOrganizeFilename =
    draft.organize_filename !== null &&
    (!draft.organize_filename || draft.organize_filename === previousAutoTitle);

  return {
    ...draft,
    video_path: nextPath,
    title: shouldRefreshTitle ? nextAutoTitle : draft.title,
    organize_filename: shouldRefreshOrganizeFilename
      ? nextAutoTitle
      : draft.organize_filename,
  };
}

function titleFromPath(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  const filename = parts.length ? parts[parts.length - 1] : path;
  const stem = filename.replace(/\.[^.]+$/, "");
  return stem.replace(/[._-]+/g, " ").replace(/\s+/g, " ").trim();
}

function listFromText(value: string): string[] {
  return unique(
    value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

function defaultLocalTags(): string[] {
  return ["local-generated", "unmatched"];
}

function batchStatusLabel(status: BatchDraftState): string {
  switch (status) {
    case "loaded":
      return "已载入";
    case "updated":
      return "已更新";
    case "drafted":
    default:
      return "草稿";
  }
}

function batchStatusClass(status: BatchDraftState): string {
  switch (status) {
    case "loaded":
      return "status-pill-neutral";
    case "updated":
      return "status-pill-success";
    case "drafted":
    default:
      return "status-pill-warning";
  }
}

function runtimeMinutes(durationSeconds: number | null): number | null {
  if (!durationSeconds || !Number.isFinite(durationSeconds)) {
    return null;
  }
  return Math.max(1, Math.round(durationSeconds / 60));
}

function formatDuration(seconds: number | null): string {
  if (!seconds || !Number.isFinite(seconds)) {
    return "未知";
  }
  const whole = Math.round(seconds);
  const minutes = Math.floor(whole / 60);
  const remainingSeconds = whole % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function formatTime(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) {
    return "--:--";
  }
  return formatDuration(seconds);
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function clampExtraBackdropCount(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.min(10, Math.max(0, parsed));
}

function clampTitleAngleDegrees(value: string): number {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.min(
    MAX_TITLE_ANGLE_DEGREES,
    Math.max(MIN_TITLE_ANGLE_DEGREES, parsed),
  );
}

function clampTitlePositionPercent(value: string): number {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return MIN_TITLE_POSITION_PERCENT;
  }
  return Math.min(
    MAX_TITLE_POSITION_PERCENT,
    Math.max(MIN_TITLE_POSITION_PERCENT, parsed),
  );
}

function organizationModeForPreview(mode: OrganizationMode): OrganizationMode {
  return mode === "in_place" ? "copy" : mode;
}
