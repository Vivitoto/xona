import { FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  CornerUpLeft,
  FileVideo,
  Folder,
  FolderOpen,
  HardDrive,
  Images,
  ListVideo,
  RefreshCw,
  X,
} from "lucide-react";

import { apiFetch } from "../api/client";
import type {
  AppSettings,
  BrowseResponse,
  CoverTemplateName,
  LocalAnalyzeResponse,
  LocalCacheCleanupResponse,
  LocalCachedAsset,
  LocalCoverPreviewRequest,
  LocalCoverPreviewResponse,
  LocalExecutePlanResponse,
  LocalFrameRequest,
  LocalFrameResponse,
  LocalMetadataDraft,
  LocalNfoPreviewResponse,
  LocalPlanPreviewRequest,
  LocalPlanPreviewResponse,
  LocalScanResponse,
  LocalScannedVideo,
  OrganizationMode,
  PosterFontId,
  PosterTextEffect,
  StorageRootList,
  StorageRootRead,
} from "../api/types";
import { DirectoryPicker } from "../components/DirectoryPicker";
import { CheckboxField, FormField, Section } from "../components/FormField";
import { Tabs, type TabItem } from "../components/Tabs";
import { linesToList, listToLines, normalizeSettings } from "./settings/settingsForm";

const coverTemplates: { value: CoverTemplateName; label: string }[] = [
  { value: "simple_poster", label: "Simple Poster" },
  { value: "jav_classic_left_strip", label: "JAV Classic" },
  { value: "tangxin_vlog", label: "TangXin Vlog" },
];
const posterFonts: { value: PosterFontId; label: string }[] = [
  { value: "source_han_sans", label: "思源黑体 / Source Han Sans" },
  { value: "noto_sans_jp", label: "Noto Sans JP" },
  { value: "noto_sans_cjk_regular", label: "Noto 黑体常规 / Noto Sans CJK" },
  { value: "noto_serif_cjk", label: "Noto 宋体 / Noto Serif CJK" },
  { value: "noto_serif_cjk_bold", label: "Noto 粗宋 / Noto Serif CJK Bold" },
  { value: "dela_gothic_one", label: "Dela Gothic One" },
  { value: "bebas_neue", label: "Bebas Neue" },
  { value: "anton", label: "Anton" },
  { value: "smiley_sans", label: "得意黑 / Smiley Sans" },
  { value: "zcool_qingke_huangyou", label: "站酷庆科黄油体" },
  { value: "zcool_kuaile", label: "站酷快乐体 / ZCOOL KuaiLe" },
  { value: "lxgw_wenkai", label: "霞鹜文楷 / LXGW WenKai" },
];
const DEFAULT_TITLE_FONT_BY_TEMPLATE: Record<CoverTemplateName, PosterFontId> = {
  simple_poster: "source_han_sans",
  jav_classic_left_strip: "dela_gothic_one",
  tangxin_vlog: "smiley_sans",
};
const RANDOM_TITLE_FONT_POOL_BY_TEMPLATE: Record<
  CoverTemplateName,
  PosterFontId[]
> = {
  simple_poster: [
    "source_han_sans",
    "noto_sans_cjk_regular",
    "noto_serif_cjk",
    "noto_serif_cjk_bold",
    "lxgw_wenkai",
  ],
  jav_classic_left_strip: [
    "dela_gothic_one",
    "noto_sans_jp",
    "source_han_sans",
    "bebas_neue",
    "anton",
  ],
  tangxin_vlog: ["smiley_sans", "zcool_qingke_huangyou", "zcool_kuaile"],
};
const DEFAULT_TITLE_ANGLE_DEGREES = -8;
const MIN_TITLE_ANGLE_DEGREES = -20;
const MAX_TITLE_ANGLE_DEGREES = 20;
const MIN_TITLE_OFFSET = -50;
const MAX_TITLE_OFFSET = 50;
const MIN_TITLE_FONT_SIZE = 16;
const MAX_TITLE_FONT_SIZE = 180;
const MIN_TITLE_STROKE_WIDTH = 0;
const MAX_TITLE_STROKE_WIDTH = 20;
const BATCH_TITLE_FONT_SIZE_JITTER_RANGE = 10;
const BATCH_TITLE_ANGLE_JITTER_RANGE = 5;
const BATCH_TITLE_OFFSET_JITTER_RANGE = 10;
const DEFAULT_SCREENSHOT_COUNT = 9;
const MIN_COVER_FRAME_COUNT = 9;
const MIN_SCREENSHOT_COUNT = MIN_COVER_FRAME_COUNT;
const MAX_SCREENSHOT_COUNT = 36;
const DEFAULT_BATCH_CONCURRENCY = 2;
const BATCH_TABLE_VISIBLE_LIMIT = 50;
const DEFAULT_LOCAL_METADATA_VALUES = ["{actors}", "{studio}", "{resolution}"];
const MIN_BATCH_CONCURRENCY = 1;
const MAX_BATCH_CONCURRENCY = 3;
const DEFAULT_TITLE_POSITION_BY_TEMPLATE: Record<
  CoverTemplateName,
  { x: number; y: number }
> = {
  simple_poster: { x: 50, y: 93.41021416803954 },
  jav_classic_left_strip: { x: 87.79069767441861, y: 96.84921230307577 },
  tangxin_vlog: { x: 50, y: 90.14522821576763 },
};
const DEFAULT_TITLE_STYLE_BY_TEMPLATE: Record<
  CoverTemplateName,
  {
    fontSize: number;
    fillColor: string;
    strokeColor: string;
    strokeWidth: number;
    effect: PosterTextEffect;
  }
> = {
  simple_poster: {
    fontSize: 74,
    fillColor: "#ffffff",
    strokeColor: "#0c1114",
    strokeWidth: 4,
    effect: "shadow",
  },
  jav_classic_left_strip: {
    fontSize: 62,
    fillColor: "#121b22",
    strokeColor: "#ffffff",
    strokeWidth: 1,
    effect: "shadow",
  },
  tangxin_vlog: {
    fontSize: 86,
    fillColor: "#ffffff",
    strokeColor: "#0e1518",
    strokeWidth: 6,
    effect: "glow",
  },
};
const titleEffects: { value: PosterTextEffect; label: string }[] = [
  { value: "shadow", label: "阴影" },
  { value: "glow", label: "发光" },
  { value: "none", label: "无" },
];

type BusyAction =
  | "analyze_frames"
  | "cover"
  | "nfo"
  | "plan"
  | "execute"
  | "scan"
  | "batch_generate"
  | "batch_execute"
  | null;

interface BatchDraftStatus {
  path: string;
  filename: string;
  draft: LocalMetadataDraft;
  coverSettings: CoverEditorSettings;
  status: BatchDraftState;
}

type BatchDraftState = "drafted";
type BatchOutputState =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "executing"
  | "executed"
  | "execute_failed";
type BatchOutputLogTone = "active" | "success" | "warning" | "danger" | "neutral";
type LocalMetadataWorkflowTab = "single" | "batch";

interface BatchOutputLog {
  tone: BatchOutputLogTone;
  message: string;
}

interface BatchOutputItem {
  path: string;
  filename: string;
  draft: LocalMetadataDraft;
  coverSettings: CoverEditorSettings;
  status: BatchOutputState;
  logs: BatchOutputLog[];
  frames: LocalCachedAsset[];
  selectedFrameIds: string[];
  coverPreview: LocalCoverPreviewResponse | null;
  planPreview: LocalPlanPreviewResponse | null;
  executeResult: LocalExecutePlanResponse | null;
  error: string | null;
}

interface CoverEditorSettings {
  template: CoverTemplateName;
  titleFontId: PosterFontId;
  titleFontSize: number;
  titleFillColor: string;
  titleStrokeColor: string;
  titleStrokeWidth: number;
  titleEffect: PosterTextEffect;
  titleAngleDegrees: number;
  titleOffsetX: number;
  titleOffsetY: number;
}

interface BatchCoverStyleSettings extends CoverEditorSettings {
  randomTitleFormat: boolean;
}

interface BatchRunOptions {
  destinationRoot: string;
  mode: OrganizationMode;
  folderTemplates: string[];
  filenameTemplate: string;
  extraBackdropCount: number;
  frameCount: number;
}

const localMetadataWorkflowTabs: readonly TabItem<LocalMetadataWorkflowTab>[] = [
  { id: "single", label: "单个整理" },
  { id: "batch", label: "批量整理" },
];

export function UnmatchedVideosPage() {
  const [activeWorkflowTab, setActiveWorkflowTab] =
    useState<LocalMetadataWorkflowTab>("single");
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
  const [titleOffsetX, setTitleOffsetX] = useState(
    titlePositionPercentToOffset(DEFAULT_TITLE_POSITION_BY_TEMPLATE.simple_poster.x),
  );
  const [titleOffsetY, setTitleOffsetY] = useState(
    titlePositionPercentToOffset(DEFAULT_TITLE_POSITION_BY_TEMPLATE.simple_poster.y),
  );
  const [screenshotCount, setScreenshotCount] = useState(DEFAULT_SCREENSHOT_COUNT);
  const [technical, setTechnical] = useState<LocalAnalyzeResponse["technical"] | null>(
    null,
  );
  const [frames, setFrames] = useState<LocalCachedAsset[]>([]);
  const [selectedFrameIds, setSelectedFrameIds] = useState<string[]>([]);
  const [template, setTemplate] = useState<CoverTemplateName>("simple_poster");
  const [titleFontId, setTitleFontId] = useState<PosterFontId>(
    DEFAULT_TITLE_FONT_BY_TEMPLATE.simple_poster,
  );
  const [titleFontSize, setTitleFontSize] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.fontSize,
  );
  const [titleFillColor, setTitleFillColor] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.fillColor,
  );
  const [titleStrokeColor, setTitleStrokeColor] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.strokeColor,
  );
  const [titleStrokeWidth, setTitleStrokeWidth] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.strokeWidth,
  );
  const [titleEffect, setTitleEffect] = useState<PosterTextEffect>(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.effect,
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
  const [batchActors, setBatchActors] = useState("");
  const [batchTags, setBatchTags] = useState(
    listToLines(DEFAULT_LOCAL_METADATA_VALUES),
  );
  const [batchGenres, setBatchGenres] = useState(
    listToLines(DEFAULT_LOCAL_METADATA_VALUES),
  );
  const [batchPlot, setBatchPlot] = useState("");
  const [batchCoverTemplate, setBatchCoverTemplate] =
    useState<CoverTemplateName>("simple_poster");
  const [batchCoverTitleFontId, setBatchCoverTitleFontId] = useState<PosterFontId>(
    DEFAULT_TITLE_FONT_BY_TEMPLATE.simple_poster,
  );
  const [batchCoverTitleFontSize, setBatchCoverTitleFontSize] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.fontSize,
  );
  const [batchCoverTitleFillColor, setBatchCoverTitleFillColor] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.fillColor,
  );
  const [batchCoverTitleStrokeColor, setBatchCoverTitleStrokeColor] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.strokeColor,
  );
  const [batchCoverTitleStrokeWidth, setBatchCoverTitleStrokeWidth] = useState(
    DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.strokeWidth,
  );
  const [batchCoverTitleEffect, setBatchCoverTitleEffect] =
    useState<PosterTextEffect>(DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.effect);
  const [batchCoverTitleAngleDegrees, setBatchCoverTitleAngleDegrees] = useState(
    DEFAULT_TITLE_ANGLE_DEGREES,
  );
  const [batchCoverTitleOffsetX, setBatchCoverTitleOffsetX] = useState(
    titlePositionPercentToOffset(DEFAULT_TITLE_POSITION_BY_TEMPLATE.simple_poster.x),
  );
  const [batchCoverTitleOffsetY, setBatchCoverTitleOffsetY] = useState(
    titlePositionPercentToOffset(DEFAULT_TITLE_POSITION_BY_TEMPLATE.simple_poster.y),
  );
  const [batchCoverRandomTitleFormat, setBatchCoverRandomTitleFormat] =
    useState(true);
  const [batchStatuses, setBatchStatuses] = useState<BatchDraftStatus[]>([]);
  const [batchConcurrency, setBatchConcurrency] = useState(
    DEFAULT_BATCH_CONCURRENCY,
  );
  const [batchOutputItems, setBatchOutputItems] = useState<BatchOutputItem[]>([]);
  const [busy, setBusy] = useState<BusyAction>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const posterTitleTouched = useRef(false);
  const titleFontTouched = useRef(false);
  const batchTitleFontTouched = useRef(false);

  const selectedVideos = useMemo(
    () => scannedVideos.filter((video) => selectedBatchPaths.includes(video.path)),
    [scannedVideos, selectedBatchPaths],
  );

  useEffect(() => {
    const selectedBatchCoverStyle = currentBatchCoverStyleSettings();
    setBatchStatuses((current) =>
      current.length
        ? current.map((item) => ({
            ...item,
            coverSettings: randomizedBatchCoverSettings(
              item.path,
              selectedBatchCoverStyle,
            ),
          }))
        : current,
    );
    setBatchOutputItems((current) => (current.length ? [] : current));
  }, [
    batchCoverTemplate,
    batchCoverTitleFontId,
    batchCoverTitleFontSize,
    batchCoverTitleFillColor,
    batchCoverTitleStrokeColor,
    batchCoverTitleStrokeWidth,
    batchCoverTitleEffect,
    batchCoverTitleAngleDegrees,
    batchCoverTitleOffsetX,
    batchCoverTitleOffsetY,
    batchCoverRandomTitleFormat,
  ]);

  const initialCoverFrameIds = useMemo(() => selectedInitialFrameIds(frames), [frames]);
  const hasSelectedFrames = selectedFrameIds.length > 0;
  const hasEnoughSelectedCoverFrames = selectedFrameIds.length >= MIN_COVER_FRAME_COUNT;
  const canReselectInitialCoverFrames =
    frames.length > 0 && !sameOrderedValues(selectedFrameIds, initialCoverFrameIds);
  const hasLocalSource = Boolean(draft.video_path.trim() || scannedVideos.length);
  const coverDisplayTitle = posterTitle.trim() || draft.title.trim();
  const canGenerateCover =
    Boolean(draft.video_path.trim() && coverDisplayTitle && hasEnoughSelectedCoverFrames) &&
    busy !== "cover";
  const canPreviewPlan =
    Boolean(draft.video_path.trim() && destinationRoot.trim()) && busy !== "plan";
  const canPreviewNfo =
    Boolean(draft.video_path.trim() && draft.title.trim()) && busy !== "nfo";
  const canExecutePlan =
    Boolean(planPreview && planPreview.plan.mode !== "preview" && !executeResult) &&
    busy !== "execute";
  const canGenerateBatchOutputs =
    Boolean(batchStatuses.length && destinationRoot.trim()) && busy === null;
  const executableBatchOutputItems = useMemo(
    () => batchOutputItems.filter(canExecuteBatchOutputItem),
    [batchOutputItems],
  );
  const canExecuteBatchOutputs =
    Boolean(executableBatchOutputItems.length) && busy === null;

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

  async function analyzeAndGenerateFrames(event?: FormEvent) {
    event?.preventDefault();
    if (!videoPath.trim()) {
      setError("请输入视频路径。");
      return;
    }
    setBusy("analyze_frames");
    setError("");
    setStatus("正在分析视频并生成截图");
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
        genres: response.default_genres,
        runtime_minutes: runtimeMinutes(response.technical.duration_seconds),
        technical: response.technical,
      };
      setDraft(nextDraft);
      resetPosterTitle(nextDraft.title);
      setStatus("正在生成截图");
      const frameResponse = await requestFrames(response.video_path);
      setFrames(frameResponse.frames);
      setSelectedFrameIds(selectedInitialFrameIds(frameResponse.frames));
      setStatus(`分析完成，已生成 ${frameResponse.frames.length} 张截图`);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "分析或截图生成失败";
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

  async function requestFrames(
    sourceVideoPath: string,
    frameCount = screenshotCount,
  ): Promise<LocalFrameResponse> {
    const body: LocalFrameRequest = {
      video_path: sourceVideoPath,
      frame_count: frameCount,
    };
    return apiFetch<LocalFrameResponse>("/api/local-metadata/frames", {
      method: "POST",
      body,
    });
  }

  async function generateCoverPreview() {
    const title = coverDisplayTitle.trim();
    if (!draft.video_path.trim() || !title) {
      setError("视频路径和封面文字不能为空。");
      return;
    }
    if (selectedFrameIds.length < MIN_COVER_FRAME_COUNT) {
      setError(`请先生成截图并选择至少 ${MIN_COVER_FRAME_COUNT} 张不同截图用于封面。`);
      return;
    }
    setBusy("cover");
    setError("");
    setStatus("正在生成封面");
    try {
      const body = buildCoverPreviewRequest({
        videoPath: draft.video_path,
        title,
        settings: currentCoverEditorSettings(),
        selectedFrameIds,
      });
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
      const body = buildPlanPreviewRequest({
        draft: cleanedDraft(draft),
        destinationRoot: destinationRoot.trim(),
        mode,
        folderTemplates: linesToList(folderTemplates),
        filenameTemplate,
        coverPreview,
        selectedFrameIds,
        extraBackdropCount,
      });
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
      setSelectedBatchPaths(response.videos.map((video) => video.path));
      setBatchStatuses([]);
      setBatchOutputItems([]);
      setStatus(`已扫描 ${response.scanned_count} 个视频文件`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "目录扫描失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  function selectVideo(video: LocalScannedVideo) {
    const title = video.cleaned_title || titleFromPath(video.path);
    loadDraftIntoEditor({
      ...blankDraft(video.path),
      title,
      organize_filename: video.default_organize_filename || title,
      plot: title,
    });
    setActiveWorkflowTab("single");
    setStatus(`已选择 ${video.filename}`);
  }

  function toggleBatchSelection(path: string, selected: boolean) {
    setSelectedBatchPaths((current) =>
      selected ? unique([...current, path]) : current.filter((item) => item !== path),
    );
  }

  function selectAllBatchVideos() {
    setSelectedBatchPaths(scannedVideos.map((video) => video.path));
  }

  function clearBatchSelection() {
    setSelectedBatchPaths([]);
  }

  function applyBatchFields() {
    const previousTechnicalByPath = new Map(
      batchStatuses.map((item) => [item.path, item.draft.technical]),
    );
    const selectedBatchCoverStyle = currentBatchCoverStyleSettings();
    const statuses = selectedVideos.map((video) => {
      const knownTechnical =
        (draft.video_path === video.path ? draft.technical ?? technical : null) ??
        previousTechnicalByPath.get(video.path) ??
        null;
      return {
        path: video.path,
        filename: video.filename,
        draft: buildBatchDraft(video, knownTechnical),
        coverSettings: randomizedBatchCoverSettings(
          video.path,
          selectedBatchCoverStyle,
        ),
        status: "drafted" as const,
      };
    });
    setBatchStatuses(statuses);
    setBatchOutputItems([]);
    setStatus(`已生成 ${statuses.length} 个批量元数据，可直接生成全部预览`);
  }

  async function generateBatchOutputs() {
    if (!batchStatuses.length) {
      setError("请先生成批量元数据。");
      return;
    }
    if (!destinationRoot.trim()) {
      setError("请输入目标目录。");
      return;
    }

    const options: BatchRunOptions = {
      destinationRoot: destinationRoot.trim(),
      mode,
      folderTemplates: linesToList(folderTemplates),
      filenameTemplate,
      extraBackdropCount,
      frameCount: screenshotCount,
    };
    const items = batchStatuses.map((item) => initialBatchOutputItem(item));
    const concurrency = clampBatchConcurrencyValue(batchConcurrency);

    setBatchOutputItems(items);
    setBusy("batch_generate");
    setError("");
    setStatus(`正在以 ${concurrency} 路并发生成全部预览`);

    try {
      const results = await runLimitedConcurrency(
        items,
        concurrency,
        async (item) => generateBatchOutputItem(item, options),
      );
      const successCount = results.filter(Boolean).length;
      const failureCount = results.length - successCount;
      setStatus(`批量生成完成：成功 ${successCount} 个，失败 ${failureCount} 个`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "批量生成失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function generateBatchOutputItem(
    item: BatchOutputItem,
    options: BatchRunOptions,
  ): Promise<boolean> {
    updateBatchOutputItem(item.path, (current) => ({
      ...current,
      status: "running",
      logs: [{ tone: "active", message: "开始处理" }],
      error: null,
    }));

    try {
      appendBatchOutputLog(item.path, "active", "正在分析视频");
      const analyzeResponse = await apiFetch<LocalAnalyzeResponse>(
        "/api/local-metadata/analyze",
        {
          method: "POST",
          body: { video_path: item.draft.video_path },
        },
      );
      const analyzedDraft = cleanedDraft({
        ...item.draft,
        video_path: analyzeResponse.video_path,
        runtime_minutes: runtimeMinutes(
          analyzeResponse.technical.duration_seconds,
        ),
        technical: analyzeResponse.technical,
      });
      updateBatchStatusDraft(item.path, analyzedDraft);
      updateBatchOutputItem(item.path, (current) => ({
        ...current,
        draft: cloneDraft(analyzedDraft),
      }));
      appendBatchOutputLog(item.path, "success", "分析完成");

      appendBatchOutputLog(
        item.path,
        "active",
        `正在生成 ${options.frameCount} 张截图`,
      );
      const frameResponse = await requestFrames(
        analyzeResponse.video_path,
        options.frameCount,
      );
      const selectedFrames = selectedInitialFrameIds(frameResponse.frames);
      if (selectedFrames.length < MIN_COVER_FRAME_COUNT) {
        throw new Error(
          `截图不足，至少需要 ${MIN_COVER_FRAME_COUNT} 张用于封面。`,
        );
      }
      updateBatchOutputItem(item.path, (current) => ({
        ...current,
        frames: frameResponse.frames,
        selectedFrameIds: selectedFrames,
      }));
      appendBatchOutputLog(
        item.path,
        "success",
        `截图完成，已选择 ${selectedFrames.length} 张封面素材`,
      );

      appendBatchOutputLog(item.path, "active", "正在生成封面预览");
      const coverRequest = buildCoverPreviewRequest({
        videoPath: analyzeResponse.video_path,
        title: analyzedDraft.title,
        settings: item.coverSettings,
        selectedFrameIds: selectedFrames,
      });
      const coverResponse = await apiFetch<LocalCoverPreviewResponse>(
        "/api/local-metadata/cover-preview",
        {
          method: "POST",
          body: coverRequest,
        },
      );
      updateBatchOutputItem(item.path, (current) => ({
        ...current,
        coverPreview: coverResponse,
      }));
      appendBatchOutputLog(item.path, "success", "封面预览已生成");

      appendBatchOutputLog(item.path, "active", "正在生成 NFO 与整理计划");
      const planRequest = buildPlanPreviewRequest({
        draft: analyzedDraft,
        destinationRoot: options.destinationRoot,
        mode: options.mode,
        folderTemplates: options.folderTemplates,
        filenameTemplate: options.filenameTemplate,
        coverPreview: coverResponse,
        selectedFrameIds: selectedFrames,
        extraBackdropCount: options.extraBackdropCount,
      });
      const planResponse = await apiFetch<LocalPlanPreviewResponse>(
        "/api/local-metadata/preview-plan",
        {
          method: "POST",
          body: planRequest,
        },
      );
      updateBatchOutputItem(item.path, (current) => ({
        ...current,
        status: "succeeded",
        planPreview: planResponse,
        error: null,
      }));
      appendBatchOutputLog(
        item.path,
        "success",
        `NFO 与整理计划已生成，计划 ${planResponse.plan_id}`,
      );
      return true;
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "批量条目生成失败";
      updateBatchOutputItem(item.path, (current) => ({
        ...current,
        status: "failed",
        error: message,
      }));
      appendBatchOutputLog(item.path, "danger", `失败：${message}`);
      return false;
    }
  }

  async function executeBatchOutputs() {
    const items = batchOutputItems.filter(canExecuteBatchOutputItem);
    if (!items.length) {
      setError("没有可执行的批量整理计划。");
      return;
    }

    const concurrency = clampBatchConcurrencyValue(batchConcurrency);
    setBusy("batch_execute");
    setError("");
    setStatus(`正在以 ${concurrency} 路并发执行批量整理计划`);
    try {
      const results = await runLimitedConcurrency(
        items,
        concurrency,
        executeBatchOutputItem,
      );
      const successCount = results.filter(Boolean).length;
      const failureCount = results.length - successCount;
      setStatus(`批量执行完成：成功 ${successCount} 个，失败 ${failureCount} 个`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "批量执行失败");
      setStatus("");
    } finally {
      setBusy(null);
    }
  }

  async function executeBatchOutputItem(item: BatchOutputItem): Promise<boolean> {
    if (!item.planPreview) {
      return false;
    }
    updateBatchOutputItem(item.path, (current) => ({
      ...current,
      status: "executing",
      error: null,
    }));
    appendBatchOutputLog(
      item.path,
      "active",
      `正在执行整理计划 ${item.planPreview.plan_id}`,
    );
    try {
      const response = await apiFetch<LocalExecutePlanResponse>(
        `/api/local-metadata/plans/${item.planPreview.plan_id}/execute`,
        {
          method: "POST",
          body: {
            approved: true,
            plan_version: item.planPreview.plan.version,
          },
        },
      );
      updateBatchOutputItem(item.path, (current) => ({
        ...current,
        status: "executed",
        executeResult: response,
        error: null,
      }));
      appendBatchOutputLog(
        item.path,
        "success",
        response.state === "completed"
          ? "整理执行完成"
          : `整理执行状态：${response.state}`,
      );
      if (response.state === "completed") {
        await cleanupExecutedBatchPlanCache(item);
      }
      return true;
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "批量条目执行失败";
      updateBatchOutputItem(item.path, (current) => ({
        ...current,
        status: "execute_failed",
        error: message,
      }));
      appendBatchOutputLog(item.path, "danger", `执行失败：${message}`);
      return false;
    }
  }

  async function cleanupExecutedBatchPlanCache(item: BatchOutputItem) {
    if (!item.planPreview) {
      return;
    }
    appendBatchOutputLog(item.path, "active", "正在清理本地元数据缓存");
    try {
      const response = await apiFetch<LocalCacheCleanupResponse>(
        `/api/local-metadata/plans/${item.planPreview.plan_id}/cleanup-cache`,
        {
          method: "POST",
          body: {
            plan_version: item.planPreview.plan.version,
          },
        },
      );
      appendBatchOutputLog(
        item.path,
        "success",
        response.deleted_directories
          ? `本地元数据缓存已清理：${response.deleted_directories} 个目录，${response.deleted_files} 个文件`
          : "本地元数据缓存无需清理",
      );
      if (response.warnings.length) {
        appendBatchOutputLog(
          item.path,
          "warning",
          `缓存清理提示：${response.warnings.join("；")}`,
        );
      }
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "缓存清理失败";
      appendBatchOutputLog(
        item.path,
        "warning",
        `本地元数据缓存清理失败：${message}`,
      );
    }
  }

  function updateBatchStatusDraft(path: string, nextDraft: LocalMetadataDraft) {
    setBatchStatuses((current) =>
      current.map((entry) =>
        entry.path === path ? { ...entry, draft: cloneDraft(nextDraft) } : entry,
      ),
    );
  }

  function updateBatchOutputItem(
    path: string,
    updater: (item: BatchOutputItem) => BatchOutputItem,
  ) {
    setBatchOutputItems((current) =>
      current.map((item) => (item.path === path ? updater(item) : item)),
    );
  }

  function appendBatchOutputLog(
    path: string,
    tone: BatchOutputLogTone,
    message: string,
  ) {
    setBatchOutputItems((current) =>
      current.map((item) =>
        item.path === path
          ? { ...item, logs: [...item.logs, { tone, message }] }
          : item,
      ),
    );
  }

  function buildBatchDraft(
    video: LocalScannedVideo,
    knownTechnical: LocalMetadataDraft["technical"] = null,
  ): LocalMetadataDraft {
    const fallbackTitle = video.cleaned_title || titleFromPath(video.path);
    const title = `${batchPrefix}${fallbackTitle}${batchSuffix}`.trim() || fallbackTitle;
    const organizeBase =
      video.default_organize_filename || video.cleaned_title || titleFromPath(video.path);
    const organizeFilename =
      `${batchFilenamePrefix}${organizeBase}${batchFilenameSuffix}`.trim() || title;
    return cleanedDraft({
      ...blankDraft(video.path),
      title,
      organize_filename: organizeFilename,
      studio: batchStudio,
      series: batchSeries,
      actors: listFromText(batchActors),
      plot: batchPlot.trim() || fallbackTitle,
      tags: listFromText(batchTags),
      genres: listFromText(batchGenres),
      runtime_minutes: runtimeMinutes(knownTechnical?.duration_seconds ?? null),
      technical: knownTechnical,
    });
  }

  function loadDraftIntoEditor(
    nextDraft: LocalMetadataDraft,
    coverSettings?: CoverEditorSettings,
  ) {
    const editorDraft = cloneDraft(nextDraft);
    setVideoPath(editorDraft.video_path);
    setDraft(editorDraft);
    resetPosterTitle(editorDraft.title);
    if (coverSettings) {
      applyCoverSettingsToEditor(coverSettings);
    }
    setTechnical(editorDraft.technical);
    clearGeneratedPreviews();
    setError("");
  }

  function updateVideoPath(nextPath: string) {
    setVideoPath(nextPath);
    setTechnical(null);
    clearGeneratedPreviews();
    const nextDraft = { ...draftWithUpdatedVideoPath(draft, nextPath), technical: null };
    setDraft(nextDraft);
    if (!posterTitleTouched.current || posterTitle === draft.title) {
      setPosterTitle(nextDraft.title);
    }
  }

  function selectVideoPath(path: string) {
    updateVideoPath(path);
    setError("");
    setStatus(`已选择视频路径：${path}`);
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
    setBatchOutputItems([]);
    setStatus("");
  }

  function currentCoverEditorSettings(): CoverEditorSettings {
    return {
      template,
      titleFontId,
      titleFontSize,
      titleFillColor,
      titleStrokeColor,
      titleStrokeWidth,
      titleEffect,
      titleAngleDegrees,
      titleOffsetX,
      titleOffsetY,
    };
  }

  function currentBatchCoverStyleSettings(): BatchCoverStyleSettings {
    return {
      template: batchCoverTemplate,
      titleFontId: batchCoverTitleFontId,
      titleFontSize: batchCoverTitleFontSize,
      titleFillColor: batchCoverTitleFillColor,
      titleStrokeColor: batchCoverTitleStrokeColor,
      titleStrokeWidth: batchCoverTitleStrokeWidth,
      titleEffect: batchCoverTitleEffect,
      titleAngleDegrees: batchCoverTitleAngleDegrees,
      titleOffsetX: batchCoverTitleOffsetX,
      titleOffsetY: batchCoverTitleOffsetY,
      randomTitleFormat: batchCoverRandomTitleFormat,
    };
  }

  function applyCoverSettingsToEditor(settings: CoverEditorSettings) {
    setTemplate(settings.template);
    setTitleFontId(settings.titleFontId);
    setTitleFontSize(clampTitleFontSizeValue(settings.titleFontSize));
    setTitleFillColor(normalizeHexColor(settings.titleFillColor, titleFillColor));
    setTitleStrokeColor(normalizeHexColor(settings.titleStrokeColor, titleStrokeColor));
    setTitleStrokeWidth(clampTitleStrokeWidthValue(settings.titleStrokeWidth));
    setTitleEffect(settings.titleEffect);
    setTitleAngleDegrees(clampTitleAngleDegreesValue(settings.titleAngleDegrees));
    setTitleOffsetX(clampTitleOffsetValue(settings.titleOffsetX));
    setTitleOffsetY(clampTitleOffsetValue(settings.titleOffsetY));
    titleFontTouched.current = true;
  }

  function updateTemplate(nextTemplate: CoverTemplateName) {
    const defaultPosition = DEFAULT_TITLE_POSITION_BY_TEMPLATE[nextTemplate];
    const defaultStyle = DEFAULT_TITLE_STYLE_BY_TEMPLATE[nextTemplate];
    setTemplate(nextTemplate);
    setTitleOffsetX(titlePositionPercentToOffset(defaultPosition.x));
    setTitleOffsetY(titlePositionPercentToOffset(defaultPosition.y));
    setTitleFontSize(defaultStyle.fontSize);
    setTitleFillColor(defaultStyle.fillColor);
    setTitleStrokeColor(defaultStyle.strokeColor);
    setTitleStrokeWidth(defaultStyle.strokeWidth);
    setTitleEffect(defaultStyle.effect);
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

  function updateTitleOffsetX(value: string) {
    setTitleOffsetX(clampTitleOffset(value));
    clearPosterDependentPreviews();
  }

  function updateTitleOffsetY(value: string) {
    setTitleOffsetY(clampTitleOffset(value));
    clearPosterDependentPreviews();
  }

  function updateTitleFontSize(value: string) {
    setTitleFontSize(clampTitleFontSize(value));
    clearPosterDependentPreviews();
  }

  function updateTitleFillColor(value: string) {
    setTitleFillColor(value);
    clearPosterDependentPreviews();
  }

  function updateTitleStrokeColor(value: string) {
    setTitleStrokeColor(value);
    clearPosterDependentPreviews();
  }

  function updateTitleStrokeWidth(value: string) {
    setTitleStrokeWidth(clampTitleStrokeWidth(value));
    clearPosterDependentPreviews();
  }

  function updateTitleEffect(value: PosterTextEffect) {
    setTitleEffect(value);
    clearPosterDependentPreviews();
  }

  function updateBatchCoverTemplate(nextTemplate: CoverTemplateName) {
    const defaultPosition = DEFAULT_TITLE_POSITION_BY_TEMPLATE[nextTemplate];
    const defaultStyle = DEFAULT_TITLE_STYLE_BY_TEMPLATE[nextTemplate];
    setBatchCoverTemplate(nextTemplate);
    setBatchCoverTitleOffsetX(titlePositionPercentToOffset(defaultPosition.x));
    setBatchCoverTitleOffsetY(titlePositionPercentToOffset(defaultPosition.y));
    setBatchCoverTitleFontSize(defaultStyle.fontSize);
    setBatchCoverTitleFillColor(defaultStyle.fillColor);
    setBatchCoverTitleStrokeColor(defaultStyle.strokeColor);
    setBatchCoverTitleStrokeWidth(defaultStyle.strokeWidth);
    setBatchCoverTitleEffect(defaultStyle.effect);
    if (!batchTitleFontTouched.current) {
      setBatchCoverTitleFontId(DEFAULT_TITLE_FONT_BY_TEMPLATE[nextTemplate]);
    }
  }

  function updateBatchCoverTitleFont(nextFontId: PosterFontId) {
    batchTitleFontTouched.current = true;
    setBatchCoverTitleFontId(nextFontId);
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

  function reselectInitialCoverFrames() {
    const nextFrameIds = selectedInitialFrameIds(frames);
    setSelectedFrameIds(nextFrameIds);
    setCoverPreview(null);
    clearPlanPreview();
    setStatus(`已重新选择前 ${nextFrameIds.length} 张截图用于 Poster/Fanart/Thumb`);
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

  function renderOrganizePreviewSection(workflow: LocalMetadataWorkflowTab) {
    return (
      <Section title="整理预览">
        <OrganizeProgressSummary
          busy={busy}
          destinationRoot={destinationRoot}
          draftVideoPath={draft.video_path}
          executeResult={executeResult}
          planPreview={planPreview}
          workflow={workflow}
        />
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
          <FormField label="额外背景图数量">
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
          <button disabled={!canPreviewPlan} type="button" onClick={previewPlan}>
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
        <LocalOrganizePreviewSummary planPreview={planPreview} />
      </Section>
    );
  }

  return (
    <div className="page-stack unmatched-workbench">
      <WorkflowProgress
        hasLocalSource={hasLocalSource}
        hasSelectedFrames={hasEnoughSelectedCoverFrames}
        hasPlanPreview={Boolean(planPreview)}
      />

      <Tabs
        activeTab={activeWorkflowTab}
        ariaLabel="本地元数据整理方式"
        tabs={localMetadataWorkflowTabs}
        onChange={setActiveWorkflowTab}
      />

      <div className="tab-panel" role="tabpanel">
        {activeWorkflowTab === "single" ? (
          <>
            <Section title="单个视频">
              <p className="section-lead">
                先分析单个文件或从批量扫描载入草稿，再生成截图并选择封面帧，最后预览
                NFO 与整理计划。
              </p>
              <form className="unmatched-source-grid" onSubmit={analyzeAndGenerateFrames}>
                <div className="path-field">
                  <FormField label="视频路径">
                    <input
                      placeholder="/media/incoming/video.mp4"
                      value={videoPath}
                      onChange={(event) => updateVideoPath(event.target.value)}
                    />
                  </FormField>
                  <VideoPathPicker
                    buttonLabel="选择视频"
                    initialPath={videoPath}
                    onSelect={selectVideoPath}
                    title="选择视频文件"
                  />
                </div>
                <FormField
                  label="截图数量"
                  description="用于截图候选和 Fanart 拼图；默认 9 张，生成后自动选中前 9 张。"
                >
                  <input
                    max={MAX_SCREENSHOT_COUNT}
                    min={MIN_SCREENSHOT_COUNT}
                    step={1}
                    type="number"
                    value={screenshotCount}
                    onChange={(event) =>
                      setScreenshotCount(clampScreenshotCount(event.target.value))
                    }
                  />
                </FormField>
                <div className="field-action">
                  <button
                    disabled={busy === "analyze_frames" || !videoPath.trim()}
                    type="submit"
                  >
                    {busy === "analyze_frames"
                      ? "分析并生成中..."
                      : "分析并生成截图"}
                  </button>
                </div>
              </form>

              {technical ? <TechnicalSummary technical={technical} /> : null}
            </Section>

            <div className="unmatched-editor-layout">
              <Section title="元数据草稿">
                <div className="grid two">
                  <FormField label="标题 (title)">
                    <input
                      value={draft.title}
                      onChange={(event) => updateDraft("title", event.target.value)}
                    />
                  </FormField>
                  <FormField
                    label="整理文件名 (organize_filename)"
                    description="标题 (title) 写入 NFO 元数据；整理文件名 (organize_filename) 用于输出视频和同名 NFO 文件。留空时使用文件名模板。"
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
                  <FormField label="封面字号">
                    <input
                      max={180}
                      min={16}
                      step={1}
                      type="number"
                      value={titleFontSize}
                      onChange={(event) => updateTitleFontSize(event.target.value)}
                    />
                  </FormField>
                  <FormField label="文字填充色">
                    <input
                      type="color"
                      value={titleFillColor}
                      onChange={(event) => updateTitleFillColor(event.target.value)}
                    />
                  </FormField>
                  <FormField label="文字效果">
                    <select
                      value={titleEffect}
                      onChange={(event) =>
                        updateTitleEffect(event.target.value as PosterTextEffect)
                      }
                    >
                      {titleEffects.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </FormField>
                </div>
                <div className="grid three">
                  <FormField label="描边颜色">
                    <input
                      type="color"
                      value={titleStrokeColor}
                      onChange={(event) => updateTitleStrokeColor(event.target.value)}
                    />
                  </FormField>
                  <FormField label="描边宽度">
                    <input
                      max={20}
                      min={0}
                      step={1}
                      type="number"
                      value={titleStrokeWidth}
                      onChange={(event) => updateTitleStrokeWidth(event.target.value)}
                    />
                  </FormField>
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
                </div>
                <div className="grid two">
                  <FormField
                    label="文字横向偏移"
                    description="0 表示居中；负数向左/上移动，正数向右/下移动。"
                  >
                    <input
                      max={MAX_TITLE_OFFSET}
                      min={MIN_TITLE_OFFSET}
                      step={1}
                      type="number"
                      value={titleOffsetX}
                      onChange={(event) => updateTitleOffsetX(event.target.value)}
                    />
                  </FormField>
                  <FormField label="文字纵向偏移">
                    <input
                      max={MAX_TITLE_OFFSET}
                      min={MIN_TITLE_OFFSET}
                      step={1}
                      type="number"
                      value={titleOffsetY}
                      onChange={(event) => updateTitleOffsetY(event.target.value)}
                    />
                  </FormField>
                </div>
                <div className="grid two">
                  <FormField label="制作方 (studio)">
                    <input
                      value={draft.studio ?? ""}
                      onChange={(event) =>
                        updateDraft("studio", event.target.value || null)
                      }
                    />
                  </FormField>
                  <FormField label="系列 (set)">
                    <input
                      value={draft.series ?? ""}
                      onChange={(event) =>
                        updateDraft("series", event.target.value || null)
                      }
                    />
                  </FormField>
                </div>
                <FormField
                  label="演员 (actor)"
                  description="每行一位演员；会写入 NFO <actor>，并可用于 {actors} 与 {first_actor} 模板。"
                >
                  <textarea
                    value={listToLines(draft.actors)}
                    onChange={(event) =>
                      updateDraft("actors", listFromText(event.target.value))
                    }
                  />
                </FormField>
                <FormField label="简介 (plot)">
                  <textarea
                    value={draft.plot ?? ""}
                    onChange={(event) =>
                      updateDraft("plot", event.target.value || null)
                    }
                  />
                </FormField>
                <div className="grid two">
                  <FormField
                    label="标签 (tag)"
                    description="每行一个 NFO <tag>；默认变量会展开为演员、片商: 制作方和分辨率。清空则不写入标签。"
                  >
                    <textarea
                      value={listToLines(draft.tags)}
                      onChange={(event) =>
                        updateDraft("tags", listFromText(event.target.value))
                      }
                    />
                  </FormField>
                  <FormField
                    label="类型 (genre)"
                    description="每行一个 NFO <genre>；默认变量会展开为演员、片商: 制作方和分辨率。清空则不写入类型。"
                  >
                    <textarea
                      value={listToLines(draft.genres)}
                      onChange={(event) =>
                        updateDraft("genres", listFromText(event.target.value))
                      }
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
                  生成截图后，Xona 会自动选中前 {MIN_COVER_FRAME_COUNT} 张作为
                  Poster/Fanart/Thumb 的素材；你可以手动调整，但封面预览仍至少需要
                  {MIN_COVER_FRAME_COUNT} 张不同截图。
                </p>
                {frames.length ? (
                  <>
                    <div className="frame-selection-toolbar">
                      <p className="frame-selection-status">
                        Xona 默认选择前 {MIN_COVER_FRAME_COUNT} 张；当前已选择{" "}
                        {selectedFrameIds.length} 张用于 Poster/Fanart/Thumb，至少需要{" "}
                        {MIN_COVER_FRAME_COUNT} 张。
                      </p>
                      <button
                        className="secondary"
                        disabled={!canReselectInitialCoverFrames}
                        type="button"
                        onClick={reselectInitialCoverFrames}
                      >
                        重新选择前 {MIN_COVER_FRAME_COUNT} 张
                      </button>
                    </div>
                    <div className="frame-strip">
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
                    </div>
                  </>
                ) : (
                  <div className="empty-state">
                    <span className="empty-state-icon" aria-hidden="true">
                      <Images size={20} strokeWidth={2.2} />
                    </span>
                    <strong>暂无截图</strong>
                    <span>
                      输入视频路径后生成截图；Xona 会自动选择前 {MIN_COVER_FRAME_COUNT} 张用于
                      Poster/Fanart/Thumb，也可手动调整。
                    </span>
                  </div>
                )}

                {coverPreview ? (
                  <div className="cover-preview-grid">
                    <PreviewImage asset={coverPreview.poster} label="Poster" />
                    <PreviewImage asset={coverPreview.fanart} label="Fanart" />
                    <PreviewImage asset={coverPreview.thumb} label="Thumb" />
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

            {renderOrganizePreviewSection("single")}
          </>
        ) : (
          <>
            <Section title="批量整理列表">
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

              <BatchDraftProgress
                batchStatuses={batchStatuses}
                busy={busy}
                scannedCount={scannedVideos.length}
                selectedCount={selectedBatchPaths.length}
              />

              {scannedVideos.length ? (
                <div className="batch-selection-panel">
                  <div className="row row-between batch-selection-toolbar">
                    <p className="muted">
                      默认已选中全部 {scannedVideos.length} 个视频；可以按需取消单项或清空后重选。
                    </p>
                    <div className="button-row">
                      <button
                        className="secondary"
                        disabled={selectedBatchPaths.length === scannedVideos.length}
                        type="button"
                        onClick={selectAllBatchVideos}
                      >
                        全选
                      </button>
                      <button
                        className="secondary"
                        disabled={!selectedBatchPaths.length}
                        type="button"
                        onClick={clearBatchSelection}
                      >
                        取消全部选中
                      </button>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <caption>本地视频批量列表</caption>
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
                </div>
              ) : (
                <div className="empty-state">
                  <span className="empty-state-icon" aria-hidden="true">
                    <ListVideo size={20} strokeWidth={2.2} />
                  </span>
                  <strong>暂无批量条目</strong>
                  <span>扫描目录后显示视频列表。</span>
                </div>
              )}

              <div className="grid three batch-draft-grid">
                <FormField label="标题前缀 (title)">
                  <input
                    value={batchPrefix}
                    onChange={(event) => setBatchPrefix(event.target.value)}
                  />
                </FormField>
                <FormField label="标题后缀 (title)">
                  <input
                    value={batchSuffix}
                    onChange={(event) => setBatchSuffix(event.target.value)}
                  />
                </FormField>
                <FormField label="整理文件名前缀 (organize_filename)">
                  <input
                    value={batchFilenamePrefix}
                    onChange={(event) => setBatchFilenamePrefix(event.target.value)}
                  />
                </FormField>
                <FormField label="整理文件名后缀 (organize_filename)">
                  <input
                    value={batchFilenameSuffix}
                    onChange={(event) => setBatchFilenameSuffix(event.target.value)}
                  />
                </FormField>
                <FormField label="制作方 (studio)">
                  <input
                    value={batchStudio}
                    onChange={(event) => setBatchStudio(event.target.value)}
                  />
                </FormField>
                <FormField label="系列 (set)">
                  <input
                    value={batchSeries}
                    onChange={(event) => setBatchSeries(event.target.value)}
                  />
                </FormField>
                <FormField label="演员 (actor)">
                  <textarea
                    value={batchActors}
                    onChange={(event) => setBatchActors(event.target.value)}
                  />
                </FormField>
                <FormField
                  label="标签 (tag)"
                  description="每行一个 NFO <tag>；默认变量会展开为演员、片商: 制作方和分辨率。清空则不写入标签。"
                >
                  <textarea
                    value={batchTags}
                    onChange={(event) => setBatchTags(event.target.value)}
                  />
                </FormField>
                <FormField
                  label="类型 (genre)"
                  description="每行一个 NFO <genre>；默认变量会展开为演员、片商: 制作方和分辨率。清空则不写入类型。"
                >
                  <textarea
                    value={batchGenres}
                    onChange={(event) => setBatchGenres(event.target.value)}
                  />
                </FormField>
                <FormField label="简介 (plot)">
                  <textarea
                    value={batchPlot}
                    onChange={(event) => setBatchPlot(event.target.value)}
                  />
                </FormField>
              </div>
              <div className="batch-cover-style-panel" aria-labelledby="batch-cover-style-title">
                <div>
                  <h3 id="batch-cover-style-title">批量封面风格</h3>
                  <p className="section-lead">
                    启用后，每个视频按路径稳定随机标题样式；字体只在当前模板的风格池内随机，颜色、镜像角度与几何微调范围固定为字号
                    +/-{BATCH_TITLE_FONT_SIZE_JITTER_RANGE}px、角度
                    +/-{BATCH_TITLE_ANGLE_JITTER_RANGE} 度、位置
                    +/-{BATCH_TITLE_OFFSET_JITTER_RANGE}。
                  </p>
                </div>
                <CheckboxField
                  checked={batchCoverRandomTitleFormat}
                  description="关闭后完全使用下方基础值；开启后按模板风格池稳定随机字体、颜色、角度和位置。"
                  label="随机标题格式"
                  onChange={setBatchCoverRandomTitleFormat}
                />
                <div className="grid three batch-cover-style-grid">
                  <FormField label="批量模板">
                    <select
                      value={batchCoverTemplate}
                      onChange={(event) =>
                        updateBatchCoverTemplate(
                          event.target.value as CoverTemplateName,
                        )
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
                    label="批量标题字体"
                    description="作为每个批量封面标题的基础字体。"
                  >
                    <select
                      value={batchCoverTitleFontId}
                      onChange={(event) =>
                        updateBatchCoverTitleFont(event.target.value as PosterFontId)
                      }
                    >
                      {posterFonts.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </FormField>
                  <FormField label="基础字号">
                    <input
                      max={MAX_TITLE_FONT_SIZE}
                      min={MIN_TITLE_FONT_SIZE}
                      step={1}
                      type="number"
                      value={batchCoverTitleFontSize}
                      onChange={(event) =>
                        setBatchCoverTitleFontSize(
                          clampTitleFontSize(event.target.value),
                        )
                      }
                    />
                  </FormField>
                  <FormField
                    label="基础填充色"
                    description="关闭随机标题格式时使用；启用时每个视频生成稳定随机填充色。"
                  >
                    <input
                      type="color"
                      value={batchCoverTitleFillColor}
                      onChange={(event) =>
                        setBatchCoverTitleFillColor(event.target.value)
                      }
                    />
                  </FormField>
                  <FormField
                    label="基础描边色"
                    description="关闭随机标题格式时使用；启用时每个视频生成强对比随机描边色。"
                  >
                    <input
                      type="color"
                      value={batchCoverTitleStrokeColor}
                      onChange={(event) =>
                        setBatchCoverTitleStrokeColor(event.target.value)
                      }
                    />
                  </FormField>
                  <FormField label="基础描边宽度">
                    <input
                      max={MAX_TITLE_STROKE_WIDTH}
                      min={MIN_TITLE_STROKE_WIDTH}
                      step={1}
                      type="number"
                      value={batchCoverTitleStrokeWidth}
                      onChange={(event) =>
                        setBatchCoverTitleStrokeWidth(
                          clampTitleStrokeWidth(event.target.value),
                        )
                      }
                    />
                  </FormField>
                  <FormField label="批量文字效果">
                    <select
                      value={batchCoverTitleEffect}
                      onChange={(event) =>
                        setBatchCoverTitleEffect(
                          event.target.value as PosterTextEffect,
                        )
                      }
                    >
                      {titleEffects.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </FormField>
                  <FormField label="基础倾斜角度">
                    <input
                      max={MAX_TITLE_ANGLE_DEGREES}
                      min={MIN_TITLE_ANGLE_DEGREES}
                      step={1}
                      type="number"
                      value={batchCoverTitleAngleDegrees}
                      onChange={(event) =>
                        setBatchCoverTitleAngleDegrees(
                          clampTitleAngleDegrees(event.target.value),
                        )
                      }
                    />
                  </FormField>
                  <FormField
                    label="基础横向偏移"
                    description="0 表示居中；负数向左移动，正数向右移动。"
                  >
                    <input
                      max={MAX_TITLE_OFFSET}
                      min={MIN_TITLE_OFFSET}
                      step={1}
                      type="number"
                      value={batchCoverTitleOffsetX}
                      onChange={(event) =>
                        setBatchCoverTitleOffsetX(clampTitleOffset(event.target.value))
                      }
                    />
                  </FormField>
                  <FormField
                    label="基础纵向偏移"
                    description="0 表示居中；负数向上移动，正数向下移动。"
                  >
                    <input
                      max={MAX_TITLE_OFFSET}
                      min={MIN_TITLE_OFFSET}
                      step={1}
                      type="number"
                      value={batchCoverTitleOffsetY}
                      onChange={(event) =>
                        setBatchCoverTitleOffsetY(clampTitleOffset(event.target.value))
                      }
                    />
                  </FormField>
                </div>
              </div>
              <div className="batch-output-rule-panel" aria-labelledby="batch-output-rule-title">
                <div>
                  <h3 id="batch-output-rule-title">批量输出规则</h3>
                  <p className="section-lead">
                    这些规则会一次性应用到所有已生成的批量元数据；点生成全部预览后，Xona 只展示汇总和紧凑列表。
                  </p>
                </div>
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
                  <FormField label="额外背景图数量">
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
              </div>
              <div className="button-row batch-actions-row">
                <FormField
                  label="批量并发数"
                  description={`限制为 ${MIN_BATCH_CONCURRENCY}-${MAX_BATCH_CONCURRENCY}，避免同时压满本地分析与截图任务。`}
                >
                  <input
                    max={MAX_BATCH_CONCURRENCY}
                    min={MIN_BATCH_CONCURRENCY}
                    step={1}
                    type="number"
                    value={batchConcurrency}
                    onChange={(event) =>
                      setBatchConcurrency(
                        clampBatchConcurrency(event.target.value),
                      )
                    }
                  />
                </FormField>
                <button
                  disabled={!selectedBatchPaths.length}
                  type="button"
                  onClick={applyBatchFields}
                >
                  生成批量元数据
                </button>
                <button
                  className="secondary"
                  disabled={!canGenerateBatchOutputs}
                  type="button"
                  onClick={() => void generateBatchOutputs()}
                >
                  {busy === "batch_generate"
                    ? "批量生成中..."
                    : "生成全部预览"}
                </button>
                <button
                  className="secondary"
                  disabled={!canExecuteBatchOutputs}
                  type="button"
                  onClick={() => void executeBatchOutputs()}
                >
                  {busy === "batch_execute"
                    ? "批量执行中..."
                    : "执行全部可执行计划"}
                </button>
              </div>

              <BatchOutputSummary batchOutputItems={batchOutputItems} busy={busy} />

              {batchStatuses.length ? (
                <CompactBatchDraftTable batchStatuses={batchStatuses} />
              ) : null}

              {batchOutputItems.length ? (
                <CompactBatchOutputTable batchOutputItems={batchOutputItems} />
              ) : null}
            </Section>
          </>
        )}
      </div>

      {status ? <p className="status floating-status">{status}</p> : null}
      {error ? <p className="status error floating-status">{error}</p> : null}
    </div>
  );
}

function VideoPathPicker({
  buttonLabel = "选择视频",
  initialPath = "",
  onSelect,
  title = "选择视频文件",
}: {
  buttonLabel?: string;
  initialPath?: string;
  onSelect: (path: string) => void;
  title?: string;
}) {
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [roots, setRoots] = useState<StorageRootRead[]>([]);
  const [selectedRoot, setSelectedRoot] = useState<StorageRootRead | null>(null);
  const [currentPath, setCurrentPath] = useState("");
  const [browseResult, setBrowseResult] = useState<BrowseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadRoots(path = initialPath) {
    setError("");
    setLoading(true);
    try {
      const response = await apiFetch<StorageRootList>("/api/storage-roots");
      const roots = Array.isArray(response.roots) ? response.roots : [];
      setRoots(roots);
      const matchingRoot = findRootForPickerPath(roots, path);
      const root = matchingRoot ?? roots[0] ?? null;
      setSelectedRoot(root);
      if (root) {
        const relativePath = matchingRoot
          ? toPickerRelativePath(path, root.path)
          : "";
        await browse(
          root,
          pathLooksLikeFile(relativePath)
            ? parentPickerPath(relativePath)
            : relativePath,
        );
      } else {
        setBrowseResult(null);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "无法加载媒体目录");
    } finally {
      setLoading(false);
    }
  }

  async function browse(root = selectedRoot, path = currentPath) {
    if (!root) {
      setError("请先配置媒体目录");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const query = new URLSearchParams({
        root_id: String(root.id),
        path,
      });
      const response = await apiFetch<BrowseResponse>(
        `/api/storage-roots/browse?${query}`,
      );
      setSelectedRoot(response.root);
      setBrowseResult(response);
      setCurrentPath(toPickerRelativePath(path, response.root.path));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "目录浏览失败");
    } finally {
      setLoading(false);
    }
  }

  function openPicker() {
    setOpen(true);
    setCurrentPath("");
    setBrowseResult(null);
    void loadRoots();
  }

  function switchRoot(root: StorageRootRead) {
    setSelectedRoot(root);
    void browse(root, "");
  }

  function enterDirectory(path: string) {
    if (!selectedRoot) {
      return;
    }
    void browse(selectedRoot, toPickerRelativePath(path, selectedRoot.path));
  }

  function goUp() {
    if (!selectedRoot) {
      return;
    }
    void browse(selectedRoot, parentPickerPath(currentPath));
  }

  function selectFile(path: string) {
    onSelect(path);
    setOpen(false);
  }

  return (
    <>
      <button
        className="secondary directory-picker-trigger"
        type="button"
        onClick={openPicker}
      >
        <FolderOpen className="button-icon" aria-hidden="true" size={15} />
        <span>{buttonLabel}</span>
      </button>
      {open ? (
        <div
          aria-labelledby={titleId}
          aria-modal="true"
          className="dialog-backdrop"
          role="dialog"
        >
          <div className="dialog directory-picker-dialog">
            <div className="row row-between">
              <div>
                <h2 id={titleId}>{title}</h2>
                <p className="muted">选择一个媒体目录，然后点击视频文件。</p>
              </div>
              <button
                className="secondary"
                type="button"
                onClick={() => setOpen(false)}
              >
                <X className="button-icon" aria-hidden="true" size={15} />
                <span>关闭</span>
              </button>
            </div>

            {roots.length ? (
              <div className="root-picker" aria-label="媒体目录列表">
                {roots.map((root) => (
                  <button
                    aria-pressed={selectedRoot?.id === root.id}
                    className="root-option"
                    key={root.id}
                    type="button"
                    onClick={() => switchRoot(root)}
                  >
                    <HardDrive className="button-icon" aria-hidden="true" size={15} />
                    <span className="root-name">{root.path}</span>
                    <span className="badge">
                      {root.source === "user" ? "用户" : "容器挂载"}
                    </span>
                  </button>
                ))}
              </div>
            ) : null}

            <div className="directory-toolbar">
              <button
                disabled={loading || !selectedRoot}
                type="button"
                onClick={() => void browse()}
              >
                <RefreshCw className="button-icon" aria-hidden="true" size={15} />
                <span>刷新</span>
              </button>
              <button
                className="secondary"
                disabled={loading || !selectedRoot || !currentPath}
                type="button"
                onClick={goUp}
              >
                <CornerUpLeft className="button-icon" aria-hidden="true" size={15} />
                <span>上一层</span>
              </button>
            </div>

            {error ? <p className="status error">{error}</p> : null}
            {browseResult && selectedRoot ? (
              <div className="directory-browser">
                <p className="directory-path">
                  当前目录：<code>{joinPickerPath(selectedRoot.path, currentPath)}</code>
                </p>
                {browseResult.entries.length ? (
                  <ul className="directory-tree" aria-label="视频路径浏览结果">
                    {browseResult.entries.map((entry) => (
                      <li key={entry.path}>
                        <button
                          aria-label={
                            entry.is_dir
                              ? `打开目录 ${entry.name}`
                              : `选择视频文件 ${entry.name}`
                          }
                          className="directory-entry"
                          type="button"
                          onClick={() =>
                            entry.is_dir
                              ? enterDirectory(entry.path)
                              : selectFile(entry.path)
                          }
                        >
                          <span className="directory-icon" aria-hidden="true">
                            {entry.is_dir ? (
                              <Folder size={18} strokeWidth={2.1} />
                            ) : (
                              <FileVideo size={18} strokeWidth={2.1} />
                            )}
                          </span>
                          <span className="directory-main">
                            <strong>{entry.name}</strong>
                            <small>{entry.path}</small>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">当前目录为空。</p>
                )}
              </div>
            ) : (
              <p className="muted">
                {loading ? "加载中..." : "请先配置或选择一个媒体目录。"}
              </p>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

function OrganizeProgressSummary({
  busy,
  destinationRoot,
  draftVideoPath,
  executeResult,
  planPreview,
  workflow,
}: {
  busy: BusyAction;
  destinationRoot: string;
  draftVideoPath: string;
  executeResult: LocalExecutePlanResponse | null;
  planPreview: LocalPlanPreviewResponse | null;
  workflow: LocalMetadataWorkflowTab;
}) {
  const workflowLabel = workflow === "single" ? "单个整理" : "批量整理";
  return (
    <p
      aria-label={`${workflowLabel}预览状态`}
      aria-live="polite"
      className="status"
      role="status"
    >
      {organizeProgressText({
        busy,
        destinationRoot,
        draftVideoPath,
        executeResult,
        planPreview,
        workflowLabel,
      })}
    </p>
  );
}

function BatchDraftProgress({
  batchStatuses,
  busy,
  scannedCount,
  selectedCount,
}: {
  batchStatuses: BatchDraftStatus[];
  busy: BusyAction;
  scannedCount: number;
  selectedCount: number;
}) {
  return (
    <p
      aria-label="批量整理进度"
      aria-live="polite"
      className="status"
      role="status"
    >
      {batchDraftProgressText({ batchStatuses, busy, scannedCount, selectedCount })}
    </p>
  );
}

function BatchOutputSummary({
  batchOutputItems,
  busy,
}: {
  batchOutputItems: BatchOutputItem[];
  busy: BusyAction;
}) {
  const stats = batchOutputStats(batchOutputItems);
  return (
    <div className="batch-summary-panel">
      <p
        aria-label="批量生成摘要"
        aria-live="polite"
        className="status"
        role="status"
      >
        {batchOutputSummaryText({ batchOutputItems, busy })}
      </p>
      {batchOutputItems.length ? (
        <dl className="batch-summary-metrics" aria-label="批量生成统计">
          <div>
            <dt>总数</dt>
            <dd>{stats.total}</dd>
          </div>
          <div>
            <dt>等待</dt>
            <dd>{stats.pending}</dd>
          </div>
          <div>
            <dt>处理中</dt>
            <dd>{stats.running}</dd>
          </div>
          <div>
            <dt>已生成</dt>
            <dd>{stats.succeeded}</dd>
          </div>
          <div>
            <dt>可执行</dt>
            <dd>{stats.executable}</dd>
          </div>
          <div>
            <dt>失败</dt>
            <dd>{stats.failed + stats.executeFailed}</dd>
          </div>
          <div>
            <dt>已执行</dt>
            <dd>{stats.executed}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}

function CompactBatchDraftTable({
  batchStatuses,
}: {
  batchStatuses: BatchDraftStatus[];
}) {
  const visibleItems = batchStatuses.slice(0, BATCH_TABLE_VISIBLE_LIMIT);
  const hiddenCount = Math.max(batchStatuses.length - visibleItems.length, 0);

  return (
    <div className="batch-compact-panel">
      <div className="row row-between batch-table-heading">
        <div>
          <h3>已生成的批量元数据</h3>
          <p className="muted">
            共 {batchStatuses.length} 个；当前只显示前 {visibleItems.length} 个，批量预览和执行仍作用于全部条目。
          </p>
        </div>
        <span className="status-pill status-pill-neutral">无需载入或保存</span>
      </div>
      {hiddenCount ? (
        <p className="status batch-limit-note">
          为避免页面过长，已折叠 {hiddenCount} 个成功元数据条目。
        </p>
      ) : null}
      <div className="table-wrap batch-compact-table">
        <table>
          <caption>已生成的批量元数据</caption>
          <thead>
            <tr>
              <th>文件</th>
              <th>标题</th>
              <th>整理文件名</th>
              <th>封面</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((item) => (
              <tr key={item.path}>
                <td>
                  <strong>{item.filename}</strong>
                  <small>{item.path}</small>
                </td>
                <td>{item.draft.title}</td>
                <td>{item.draft.organize_filename || "使用文件名模板"}</td>
                <td>{coverSettingsSummary(item.coverSettings)}</td>
                <td>
                  <span className={`status-pill ${batchStatusClass(item.status)}`}>
                    {batchStatusLabel(item.status)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CompactBatchOutputTable({
  batchOutputItems,
}: {
  batchOutputItems: BatchOutputItem[];
}) {
  const visibleItems = prioritizedBatchOutputItems(batchOutputItems).slice(
    0,
    BATCH_TABLE_VISIBLE_LIMIT,
  );
  const hiddenCount = Math.max(batchOutputItems.length - visibleItems.length, 0);

  return (
    <div className="batch-compact-panel batch-output-results">
      <div className="row row-between batch-table-heading">
        <div>
          <h3>批量预览结果</h3>
          <p className="muted">
            优先显示失败、处理中和可执行条目；日志、封面和计划细节默认折叠。
          </p>
        </div>
        <span className="status-pill status-pill-neutral">
          显示 {visibleItems.length} / {batchOutputItems.length}
        </span>
      </div>
      {hiddenCount ? (
        <p className="status batch-limit-note">
          已隐藏 {hiddenCount} 个低优先级条目，避免 100+ 文件时页面过长；批量执行仍覆盖全部可执行计划。
        </p>
      ) : null}
      <div className="table-wrap batch-compact-table">
        <table>
          <caption>批量预览结果</caption>
          <thead>
            <tr>
              <th>文件</th>
              <th>标题 / 计划</th>
              <th>状态</th>
              <th>执行</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((item) => (
              <tr key={item.path}>
                <td>
                  <strong>{item.filename}</strong>
                  <small>{item.path}</small>
                </td>
                <td>
                  <strong>{item.draft.title}</strong>
                  <small>
                    {item.planPreview
                      ? `计划 ${item.planPreview.plan_id}`
                      : item.draft.organize_filename || "等待计划"}
                  </small>
                </td>
                <td>
                  <span
                    className={`status-pill ${batchOutputStatusClass(item.status)}`}
                  >
                    {batchOutputStatusLabel(item.status)}
                  </span>
                  {item.error ? (
                    <p className="status error batch-output-error">
                      {shortBatchError(item.error)}
                    </p>
                  ) : null}
                </td>
                <td>{batchOutputExecutionLabel(item)}</td>
                <td>
                  <BatchOutputDetails item={item} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BatchOutputDetails({ item }: { item: BatchOutputItem }) {
  return (
    <details className="batch-output-disclosure">
      <summary>查看详情</summary>
      <div className="batch-output-details">
        <span>{item.planPreview ? "NFO 已生成" : "NFO 未生成"}</span>
        <span>
          {item.coverPreview ? `封面 ${item.coverPreview.poster.id}` : "封面未生成"}
        </span>
        <span>
          {item.planPreview ? `计划 ${item.planPreview.plan_id}` : "计划未生成"}
        </span>
        {item.planPreview ? (
          <span>目标 {item.planPreview.plan.target_directory}</span>
        ) : null}
      </div>
      <BatchOutputLogView logs={item.logs} />
    </details>
  );
}

function BatchOutputLogView({ logs }: { logs: BatchOutputLog[] }) {
  return (
    <div className="progress-log" aria-label="批量条目日志">
      {logs.length ? (
        <ol>
          {logs.map((entry, index) => (
            <li className={batchOutputLogClass(entry.tone)} key={index}>
              <span aria-hidden="true" />
              <p>{entry.message}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">等待处理。</p>
      )}
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
    <figure className={`cover-preview cover-preview-${label.toLowerCase()}`}>
      <img alt={`${label} preview`} src={asset.url} />
      <figcaption>
        {label} · {asset.width ?? "?"} x {asset.height ?? "?"}
      </figcaption>
    </figure>
  );
}

function LocalOrganizePreviewSummary({
  planPreview,
}: {
  planPreview: LocalPlanPreviewResponse | null;
}) {
  if (!planPreview) {
    return <p className="muted">尚无整理输出预览。</p>;
  }

  const outputs = organizePreviewOutputs(planPreview.plan);
  return (
    <div className="local-organize-summary" aria-label="整理输出概要">
      <div className="plan-summary">
        <span>计划 {planPreview.plan_id}</span>
        <span>模式 {planPreview.plan.mode}</span>
        <span>目标目录 {planPreview.plan.target_directory}</span>
      </div>
      <dl className="metadata-list compact organize-output-metadata">
        <div>
          <dt>目标目录</dt>
          <dd>{planPreview.plan.target_directory}</dd>
        </div>
        <div>
          <dt>目标文件</dt>
          <dd>{outputs.length} 个</dd>
        </div>
      </dl>
      <div className="plan-list local-output-list">
        <h3>目标文件</h3>
        {outputs.length ? (
          <ul>
            {outputs.map((output) => (
              <li key={output.targetPath}>
                <span>{output.kindLabel}</span>
                <code>{output.relativePath}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">暂无目标文件。</p>
        )}
      </div>
    </div>
  );
}

function organizePreviewOutputs(plan: LocalPlanPreviewResponse["plan"]): {
  targetPath: string;
  relativePath: string;
  kindLabel: string;
}[] {
  const seen = new Set<string>();
  return plan.steps
    .filter((step) => step.target_path)
    .map((step) => ({
      targetPath: step.target_path,
      relativePath: relativeTargetPath(step.target_path, plan.target_directory),
      kindLabel: outputKindLabel(step),
    }))
    .filter((output) => {
      if (seen.has(output.targetPath)) {
        return false;
      }
      seen.add(output.targetPath);
      return true;
    });
}

function relativeTargetPath(targetPath: string, targetDirectory: string): string {
  const normalizedTarget = normalizePreviewPath(targetPath);
  const normalizedDirectory = normalizePreviewPath(targetDirectory).replace(
    /\/+$/g,
    "",
  );
  if (normalizedTarget === normalizedDirectory) {
    return normalizedTarget.split("/").pop() || normalizedTarget;
  }
  if (normalizedTarget.startsWith(`${normalizedDirectory}/`)) {
    return normalizedTarget.slice(normalizedDirectory.length + 1);
  }
  return targetPath;
}

function outputKindLabel(
  step: LocalPlanPreviewResponse["plan"]["steps"][number],
): string {
  if (step.category === "media") {
    return "视频";
  }
  if (step.category === "generated_artifact") {
    return step.target_path.toLowerCase().endsWith(".nfo") ? "NFO" : "生成文件";
  }
  if (step.category === "asset") {
    const filename = step.target_path.split(/[\\/]/).pop()?.toLowerCase() ?? "";
    if (filename === "poster.jpg") {
      return "Poster";
    }
    if (filename === "fanart.jpg") {
      return "Fanart";
    }
    if (filename === "thumb.jpg") {
      return "Thumb";
    }
    if (/^backdrop\d*\.jpg$/.test(filename)) {
      return "Backdrop";
    }
    return "图片";
  }
  if (step.category === "sidecar") {
    return "附属文件";
  }
  if (step.category === "actor_output") {
    return "演员图片";
  }
  return "文件";
}

function normalizePreviewPath(path: string): string {
  return path.replace(/\\/g, "/");
}

function blankDraft(videoPath: string): LocalMetadataDraft {
  const title = videoPath ? titleFromPath(videoPath) : "";
  return {
    video_path: videoPath,
    title,
    organize_filename: title,
    plot: null,
    tags: [...DEFAULT_LOCAL_METADATA_VALUES],
    studio: null,
    series: null,
    release_date: null,
    runtime_minutes: null,
    genres: [...DEFAULT_LOCAL_METADATA_VALUES],
    actors: [],
    technical: null,
  };
}

function cloneDraft(draft: LocalMetadataDraft): LocalMetadataDraft {
  return {
    ...draft,
    tags: [...draft.tags],
    genres: [...draft.genres],
    actors: [...(draft.actors ?? [])],
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
    actors: unique((draft.actors ?? []).map((actor) => actor.trim()).filter(Boolean)),
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

function findRootForPickerPath(
  roots: StorageRootRead[],
  path: string,
): StorageRootRead | null {
  const normalizedPath = normalizePickerSeparators(path);
  if (!normalizedPath) {
    return null;
  }
  return (
    roots
      .filter((root) => {
        const rootPath = normalizePickerSeparators(root.path).replace(/\/+$/g, "");
        return (
          normalizedPath === rootPath ||
          normalizedPath.startsWith(`${rootPath}/`)
        );
      })
      .sort((left, right) => right.path.length - left.path.length)[0] ?? null
  );
}

function toPickerRelativePath(path: string, rootPath: string): string {
  const normalizedPath = normalizePickerSeparators(path);
  const normalizedRoot = normalizePickerSeparators(rootPath).replace(/\/+$/g, "");
  if (!normalizedPath || normalizedPath === normalizedRoot) {
    return "";
  }
  if (normalizedPath.startsWith(`${normalizedRoot}/`)) {
    return normalizedPath.slice(normalizedRoot.length + 1);
  }
  return normalizedPath.replace(/^\/+/, "");
}

function parentPickerPath(path: string): string {
  const normalized = normalizePickerSeparators(path).replace(/\/+$/g, "");
  if (!normalized) {
    return "";
  }
  const index = normalized.lastIndexOf("/");
  return index <= 0 ? "" : normalized.slice(0, index);
}

function joinPickerPath(rootPath: string, relativePath: string): string {
  const normalizedRoot = normalizePickerSeparators(rootPath).replace(/\/+$/g, "");
  const normalizedRelative = normalizePickerSeparators(relativePath).replace(
    /^\/+/,
    "",
  );
  return normalizedRelative
    ? `${normalizedRoot}/${normalizedRelative}`
    : normalizedRoot;
}

function normalizePickerSeparators(path: string): string {
  return path.trim().replace(/\\/g, "/");
}

function pathLooksLikeFile(path: string): boolean {
  return /[^/]+\.[^/.]+$/.test(path);
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

function organizeProgressText({
  busy,
  destinationRoot,
  draftVideoPath,
  executeResult,
  planPreview,
  workflowLabel,
}: {
  busy: BusyAction;
  destinationRoot: string;
  draftVideoPath: string;
  executeResult: LocalExecutePlanResponse | null;
  planPreview: LocalPlanPreviewResponse | null;
  workflowLabel: string;
}): string {
  if (busy === "plan") {
    return `${workflowLabel}预览状态：正在生成整理预览。`;
  }
  if (busy === "execute") {
    return `${workflowLabel}预览状态：正在执行整理计划。`;
  }
  if (busy === "batch_generate") {
    return `${workflowLabel}预览状态：正在生成全部预览。`;
  }
  if (busy === "batch_execute") {
    return `${workflowLabel}预览状态：正在执行批量整理计划。`;
  }
  if (executeResult) {
    const stateLabel =
      executeResult.state === "completed"
        ? "整理完成"
        : `状态 ${executeResult.state}`;
    return `${workflowLabel}预览状态：计划 ${executeResult.plan_id} ${stateLabel}。`;
  }
  if (planPreview) {
    return `${workflowLabel}预览状态：整理预览已生成，计划 ${planPreview.plan_id}。`;
  }
  if (!draftVideoPath.trim()) {
    return `${workflowLabel}预览状态：等待视频路径或已载入的整理信息。`;
  }
  if (!destinationRoot.trim()) {
    return `${workflowLabel}预览状态：等待目标目录。`;
  }
  return `${workflowLabel}预览状态：可生成整理预览。`;
}

function batchDraftProgressText({
  batchStatuses,
  busy,
  scannedCount,
  selectedCount,
}: {
  batchStatuses: BatchDraftStatus[];
  busy: BusyAction;
  scannedCount: number;
  selectedCount: number;
}): string {
  if (busy === "scan") {
    return "批量整理进度：正在扫描目录。";
  }
  if (busy === "batch_generate") {
    return "批量整理进度：正在生成全部预览。";
  }
  if (busy === "batch_execute") {
    return "批量整理进度：正在执行批量整理计划。";
  }
  if (batchStatuses.length) {
    return `批量整理进度：已生成 ${batchStatuses.length} 个批量元数据，可直接生成全部预览。`;
  }
  if (scannedCount) {
    return `批量整理进度：已扫描 ${scannedCount} 个视频，已选择 ${selectedCount} 个。`;
  }
  return "批量整理进度：等待扫描目录。";
}

function batchOutputSummaryText({
  batchOutputItems,
  busy,
}: {
  batchOutputItems: BatchOutputItem[];
  busy: BusyAction;
}): string {
  if (!batchOutputItems.length) {
    return "批量生成摘要：等待生成 NFO、封面与整理预览。";
  }
  const stats = batchOutputStats(batchOutputItems);

  if (busy === "batch_generate" || busy === "batch_execute") {
    return `批量生成摘要：共 ${stats.total} 个，处理中 ${stats.running} 个，等待 ${stats.pending} 个，成功 ${stats.succeeded} 个，失败 ${stats.failed + stats.executeFailed} 个，可执行 ${stats.executable} 个。`;
  }
  return `批量生成摘要：共 ${stats.total} 个，成功 ${stats.succeeded} 个，失败 ${stats.failed} 个，可执行 ${stats.executable} 个，已执行 ${stats.executed} 个，执行失败 ${stats.executeFailed} 个。`;
}

function batchOutputStats(items: BatchOutputItem[]) {
  return {
    total: items.length,
    pending: items.filter((item) => item.status === "pending").length,
    running: items.filter(
      (item) => item.status === "running" || item.status === "executing",
    ).length,
    succeeded: items.filter(
      (item) =>
        item.status === "succeeded" ||
        item.status === "executing" ||
        item.status === "executed",
    ).length,
    executable: items.filter(canExecuteBatchOutputItem).length,
    failed: items.filter((item) => item.status === "failed").length,
    executed: items.filter((item) => item.status === "executed").length,
    executeFailed: items.filter((item) => item.status === "execute_failed").length,
  };
}

function prioritizedBatchOutputItems(items: BatchOutputItem[]): BatchOutputItem[] {
  const priority: Record<BatchOutputState, number> = {
    failed: 0,
    execute_failed: 1,
    running: 2,
    executing: 3,
    succeeded: 4,
    pending: 5,
    executed: 6,
  };
  return [...items].sort((left, right) => {
    const leftPriority = priority[left.status];
    const rightPriority = priority[right.status];
    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority;
    }
    return left.filename.localeCompare(right.filename, "zh-Hans-CN");
  });
}

function batchOutputExecutionLabel(item: BatchOutputItem): string {
  if (item.executeResult) {
    return item.executeResult.state === "completed"
      ? "整理完成"
      : `状态 ${item.executeResult.state}`;
  }
  if (item.planPreview?.plan.mode === "preview") {
    return "仅预览";
  }
  if (canExecuteBatchOutputItem(item)) {
    return "可执行";
  }
  if (item.planPreview) {
    return "等待批量执行";
  }
  return "未生成计划";
}

function shortBatchError(message: string): string {
  return message.length > 96 ? `${message.slice(0, 96)}...` : message;
}

function batchStatusLabel(status: BatchDraftState): string {
  return status === "drafted" ? "已生成" : "已生成";
}

function batchStatusClass(status: BatchDraftState): string {
  return status === "drafted" ? "status-pill-success" : "status-pill-success";
}

function batchOutputStatusLabel(status: BatchOutputState): string {
  switch (status) {
    case "running":
      return "生成中";
    case "succeeded":
      return "已生成";
    case "failed":
      return "生成失败";
    case "executing":
      return "执行中";
    case "executed":
      return "已执行";
    case "execute_failed":
      return "执行失败";
    case "pending":
    default:
      return "等待";
  }
}

function batchOutputStatusClass(status: BatchOutputState): string {
  switch (status) {
    case "succeeded":
    case "executed":
      return "status-pill-success";
    case "failed":
    case "execute_failed":
      return "status-pill-danger";
    case "running":
    case "executing":
      return "status-pill-neutral";
    case "pending":
    default:
      return "status-pill-warning";
  }
}

function batchOutputLogClass(tone: BatchOutputLogTone): string {
  const suffix = tone === "neutral" ? "" : ` progress-log-line-${tone}`;
  return `progress-log-line${suffix}`;
}

function canExecuteBatchOutputItem(item: BatchOutputItem): boolean {
  return Boolean(
    item.planPreview &&
      item.planPreview.plan.mode !== "preview" &&
      !item.executeResult &&
      (item.status === "succeeded" || item.status === "execute_failed"),
  );
}

function buildCoverPreviewRequest({
  videoPath,
  title,
  settings,
  selectedFrameIds,
}: {
  videoPath: string;
  title: string;
  settings: CoverEditorSettings;
  selectedFrameIds: string[];
}): LocalCoverPreviewRequest {
  return {
    video_path: videoPath,
    title,
    title_angle_degrees: settings.titleAngleDegrees,
    title_position_x_percent: titleOffsetToTitlePositionPercent(settings.titleOffsetX),
    title_position_y_percent: titleOffsetToTitlePositionPercent(settings.titleOffsetY),
    template: settings.template,
    title_font_id: settings.titleFontId,
    title_font_size: settings.titleFontSize,
    title_fill_color: settings.titleFillColor,
    title_stroke_color: settings.titleStrokeColor,
    title_stroke_width: settings.titleStrokeWidth,
    title_effect: settings.titleEffect,
    selected_frame_ids: selectedFrameIds,
  };
}

function buildPlanPreviewRequest({
  draft,
  destinationRoot,
  mode,
  folderTemplates,
  filenameTemplate,
  coverPreview,
  selectedFrameIds,
  extraBackdropCount,
}: {
  draft: LocalMetadataDraft;
  destinationRoot: string;
  mode: OrganizationMode;
  folderTemplates: string[];
  filenameTemplate: string;
  coverPreview: LocalCoverPreviewResponse | null;
  selectedFrameIds: string[];
  extraBackdropCount: number;
}): LocalPlanPreviewRequest {
  return {
    metadata: cleanedDraft(draft),
    destination_root: destinationRoot,
    mode,
    folder_templates: folderTemplates,
    filename_template: filenameTemplate,
    poster_ref: coverPreview?.poster.id ?? null,
    fanart_ref: coverPreview?.fanart.id ?? null,
    thumb_ref: coverPreview?.thumb.id ?? null,
    selected_frame_ids: selectedFrameIds,
    extra_backdrop_count: extraBackdropCount,
  };
}

function initialBatchOutputItem(item: BatchDraftStatus): BatchOutputItem {
  return {
    path: item.path,
    filename: item.filename,
    draft: cloneDraft(item.draft),
    coverSettings: item.coverSettings,
    status: "pending",
    logs: [],
    frames: [],
    selectedFrameIds: [],
    coverPreview: null,
    planPreview: null,
    executeResult: null,
    error: null,
  };
}

function randomizedBatchCoverSettings(
  videoPath: string,
  settings: BatchCoverStyleSettings,
): CoverEditorSettings {
  const baseline = baselineBatchCoverSettings(settings);
  if (!settings.randomTitleFormat) {
    return baseline;
  }

  const seed = batchCoverSeed(videoPath, settings);
  const baseAngle =
    Math.abs(baseline.titleAngleDegrees) * stableRandomSign(seed, "angle-sign");
  const titleColors = stableRandomTitleColors(seed);

  return {
    template: baseline.template,
    titleFontId: stableRandomPosterFontId(
      seed,
      baseline.template,
      baseline.titleFontId,
    ),
    titleFontSize: clampTitleFontSizeValue(
      Math.round(
        baseline.titleFontSize +
          stableRandomDelta(
            seed,
            "font-size",
            BATCH_TITLE_FONT_SIZE_JITTER_RANGE,
          ),
      ),
    ),
    titleFillColor: titleColors.fillColor,
    titleStrokeColor: titleColors.strokeColor,
    titleStrokeWidth: baseline.titleStrokeWidth,
    titleEffect: baseline.titleEffect,
    titleAngleDegrees: clampTitleAngleDegreesValue(
      Math.round(
        baseAngle +
          stableRandomDelta(seed, "angle", BATCH_TITLE_ANGLE_JITTER_RANGE),
      ),
    ),
    titleOffsetX: clampTitleOffsetValue(
      Math.round(
        baseline.titleOffsetX +
          stableRandomDelta(seed, "offset-x", BATCH_TITLE_OFFSET_JITTER_RANGE),
      ),
    ),
    titleOffsetY: clampTitleOffsetValue(
      Math.round(
        baseline.titleOffsetY +
          stableRandomDelta(seed, "offset-y", BATCH_TITLE_OFFSET_JITTER_RANGE),
      ),
    ),
  };
}

function baselineBatchCoverSettings(
  settings: BatchCoverStyleSettings,
): CoverEditorSettings {
  return {
    template: settings.template,
    titleFontId: settings.titleFontId,
    titleFontSize: clampTitleFontSizeValue(settings.titleFontSize),
    titleFillColor: normalizeHexColor(
      settings.titleFillColor,
      DEFAULT_TITLE_STYLE_BY_TEMPLATE[settings.template].fillColor,
    ),
    titleStrokeColor: normalizeHexColor(
      settings.titleStrokeColor,
      DEFAULT_TITLE_STYLE_BY_TEMPLATE[settings.template].strokeColor,
    ),
    titleStrokeWidth: clampTitleStrokeWidthValue(settings.titleStrokeWidth),
    titleEffect: settings.titleEffect,
    titleAngleDegrees: clampTitleAngleDegreesValue(settings.titleAngleDegrees),
    titleOffsetX: clampTitleOffsetValue(settings.titleOffsetX),
    titleOffsetY: clampTitleOffsetValue(settings.titleOffsetY),
  };
}

function batchCoverSeed(
  videoPath: string,
  settings: BatchCoverStyleSettings,
): string {
  return [
    "xona-batch-cover-v2",
    videoPath,
    settings.template,
    settings.titleFontId,
    settings.titleFontSize,
    settings.titleFillColor.toLowerCase(),
    settings.titleStrokeColor.toLowerCase(),
    settings.titleStrokeWidth,
    settings.titleEffect,
    settings.titleAngleDegrees,
    settings.titleOffsetX,
    settings.titleOffsetY,
    settings.randomTitleFormat ? "random-title-format" : "fixed-title-format",
  ].join("\u001f");
}

function stableRandomDelta(seed: string, salt: string, range: number): number {
  if (range <= 0) {
    return 0;
  }
  return (stableUnitRandom(`${seed}\u001f${salt}`) * 2 - 1) * range;
}

function stableRandomSign(seed: string, salt: string): 1 | -1 {
  return stableUnitRandom(`${seed}\u001f${salt}`) < 0.5 ? -1 : 1;
}

function stableRandomPosterFontId(
  seed: string,
  template: CoverTemplateName,
  baselineFontId: PosterFontId,
): PosterFontId {
  const templatePool = RANDOM_TITLE_FONT_POOL_BY_TEMPLATE[template];
  const candidates = templatePool.length ? templatePool : [baselineFontId];
  const index = Math.floor(stableUnitRandom(`${seed}\u001ffont-id`) * candidates.length);
  return candidates[Math.min(index, candidates.length - 1)];
}

function stableUnitRandom(seed: string): number {
  let hash = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 0x100000000;
}

function parseHexColor(value: string): [number, number, number] | null {
  const match = /^#([0-9a-fA-F]{6})$/.exec(value);
  if (!match) {
    return null;
  }
  const hex = match[1];
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
  ];
}

function normalizeHexColor(value: string, fallback: string): string {
  return parseHexColor(value) ? value.toLowerCase() : fallback;
}

function stableRandomTitleColors(seed: string): {
  fillColor: string;
  strokeColor: string;
} {
  const fillIsLight = stableUnitRandom(`${seed}\u001ffill-lightness`) >= 0.5;
  const fillColor = randomVibrantColor(seed, "fill", fillIsLight);
  const fill = parseHexColor(fillColor);
  if (!fill) {
    return { fillColor: "#ffffff", strokeColor: "#071018" };
  }

  for (let attempt = 0; attempt < 18; attempt += 1) {
    const strokeColor = randomVibrantColor(
      seed,
      `stroke-${attempt}`,
      !fillIsLight,
    );
    const stroke = parseHexColor(strokeColor);
    if (stroke && hasStrongTitleContrast(fill, stroke)) {
      return { fillColor, strokeColor };
    }
  }

  const fallbackStrokeColor = randomExtremeContrastColor(
    seed,
    "stroke-fallback",
    !fillIsLight,
  );
  const fallbackStroke = parseHexColor(fallbackStrokeColor);
  if (fallbackStroke && hasStrongTitleContrast(fill, fallbackStroke)) {
    return { fillColor, strokeColor: fallbackStrokeColor };
  }

  return {
    fillColor,
    strokeColor: relativeLuminance(fill) > 0.35 ? "#071018" : "#ffffff",
  };
}

function randomVibrantColor(
  seed: string,
  salt: string,
  light: boolean,
): string {
  const hue = Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fh`) * 359);
  const saturation =
    72 + Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fs`) * 24);
  const lightness = light
    ? 70 + Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fl`) * 16)
    : 14 + Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fl`) * 14);
  return rgbToHex(hslToRgb(hue, saturation, lightness));
}

function randomExtremeContrastColor(
  seed: string,
  salt: string,
  light: boolean,
): string {
  const hue = Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fh`) * 359);
  const saturation =
    84 + Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fs`) * 16);
  const lightness = light
    ? 92 + Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fl`) * 6)
    : 4 + Math.round(stableUnitRandom(`${seed}\u001f${salt}\u001fl`) * 8);
  return rgbToHex(hslToRgb(hue, saturation, lightness));
}

function hslToRgb(
  hue: number,
  saturationPercent: number,
  lightnessPercent: number,
): [number, number, number] {
  const saturation = saturationPercent / 100;
  const lightness = lightnessPercent / 100;
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const huePrime = hue / 60;
  const x = chroma * (1 - Math.abs((huePrime % 2) - 1));
  const [red1, green1, blue1] =
    huePrime < 1
      ? [chroma, x, 0]
      : huePrime < 2
        ? [x, chroma, 0]
        : huePrime < 3
          ? [0, chroma, x]
          : huePrime < 4
            ? [0, x, chroma]
            : huePrime < 5
              ? [x, 0, chroma]
              : [chroma, 0, x];
  const match = lightness - chroma / 2;
  return [
    Math.round((red1 + match) * 255),
    Math.round((green1 + match) * 255),
    Math.round((blue1 + match) * 255),
  ];
}

function rgbToHex([red, green, blue]: [number, number, number]): string {
  return `#${[red, green, blue]
    .map((channel) => channel.toString(16).padStart(2, "0"))
    .join("")}`;
}

function hasStrongTitleContrast(
  fill: [number, number, number],
  stroke: [number, number, number],
): boolean {
  return colorContrastRatio(fill, stroke) >= 4.5 && colorDistance(fill, stroke) >= 140;
}

function colorContrastRatio(
  first: [number, number, number],
  second: [number, number, number],
): number {
  const firstLuminance = relativeLuminance(first);
  const secondLuminance = relativeLuminance(second);
  const lighter = Math.max(firstLuminance, secondLuminance);
  const darker = Math.min(firstLuminance, secondLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

function colorDistance(
  first: [number, number, number],
  second: [number, number, number],
): number {
  return Math.hypot(
    first[0] - second[0],
    first[1] - second[1],
    first[2] - second[2],
  );
}

function relativeLuminance([red, green, blue]: [number, number, number]): number {
  return 0.2126 * srgbToLinear(red) + 0.7152 * srgbToLinear(green) + 0.0722 * srgbToLinear(blue);
}

function srgbToLinear(channel: number): number {
  const normalized = channel / 255;
  return normalized <= 0.03928
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
}

function coverSettingsSummary(settings: CoverEditorSettings): string {
  return `${coverTemplateLabel(settings.template)} / ${posterFontLabel(
    settings.titleFontId,
  )} / ${settings.titleFontSize}px / ${settings.titleFillColor} -> ${
    settings.titleStrokeColor
  } / ${formatSignedNumber(
    settings.titleAngleDegrees,
  )} 度 / X ${formatSignedNumber(settings.titleOffsetX)} Y ${formatSignedNumber(
    settings.titleOffsetY,
  )}`;
}

function coverTemplateLabel(template: CoverTemplateName): string {
  return coverTemplates.find((item) => item.value === template)?.label ?? template;
}

function posterFontLabel(fontId: PosterFontId): string {
  return posterFonts.find((item) => item.value === fontId)?.label ?? fontId;
}

function formatSignedNumber(value: number): string {
  const rounded = Number.isInteger(value) ? value : Number(value.toFixed(1));
  return rounded > 0 ? `+${rounded}` : String(rounded);
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
  return clampTitleAngleDegreesValue(parsed);
}

function clampTitleOffset(value: string): number {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return clampTitleOffsetValue(parsed);
}

function titlePositionPercentToOffset(percent: number): number {
  return clampTitleOffset(String(percent - 50));
}

function titleOffsetToTitlePositionPercent(offset: number): number {
  return Math.min(100, Math.max(0, offset + 50));
}

function clampScreenshotCount(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_SCREENSHOT_COUNT;
  }
  return Math.min(MAX_SCREENSHOT_COUNT, Math.max(MIN_SCREENSHOT_COUNT, parsed));
}

function clampBatchConcurrency(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_BATCH_CONCURRENCY;
  }
  return clampBatchConcurrencyValue(parsed);
}

function clampBatchConcurrencyValue(value: number): number {
  return Math.round(
    clampNumber(value, MIN_BATCH_CONCURRENCY, MAX_BATCH_CONCURRENCY),
  );
}

function clampTitleFontSize(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_TITLE_STYLE_BY_TEMPLATE.simple_poster.fontSize;
  }
  return clampTitleFontSizeValue(parsed);
}

function clampTitleStrokeWidth(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return clampTitleStrokeWidthValue(parsed);
}

function clampTitleAngleDegreesValue(value: number): number {
  return clampNumber(value, MIN_TITLE_ANGLE_DEGREES, MAX_TITLE_ANGLE_DEGREES);
}

function clampTitleOffsetValue(value: number): number {
  return Math.round(clampNumber(value, MIN_TITLE_OFFSET, MAX_TITLE_OFFSET));
}

function clampTitleFontSizeValue(value: number): number {
  return Math.round(clampNumber(value, MIN_TITLE_FONT_SIZE, MAX_TITLE_FONT_SIZE));
}

function clampTitleStrokeWidthValue(value: number): number {
  return Math.round(
    clampNumber(value, MIN_TITLE_STROKE_WIDTH, MAX_TITLE_STROKE_WIDTH),
  );
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function selectedInitialFrameIds(frames: LocalCachedAsset[]): string[] {
  return unique(frames.map((frame) => frame.id)).slice(0, MIN_COVER_FRAME_COUNT);
}

function sameOrderedValues(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function organizationModeForPreview(mode: OrganizationMode): OrganizationMode {
  return mode === "in_place" ? "copy" : mode;
}

async function runLimitedConcurrency<T, R>(
  items: T[],
  concurrency: number,
  task: (item: T) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const workerCount = Math.min(
    clampBatchConcurrencyValue(concurrency),
    items.length,
  );

  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (nextIndex < items.length) {
        const currentIndex = nextIndex;
        nextIndex += 1;
        results[currentIndex] = await task(items[currentIndex]);
      }
    }),
  );

  return results;
}
