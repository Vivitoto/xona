import type {
  CoverTemplateName,
  LocalCachedAsset,
  LocalCoverPreviewResponse,
  LocalExecutePlanResponse,
  LocalMetadataDraft,
  LocalPlanPreviewResponse,
  OrganizationMode,
  PosterFontId,
  PosterTextEffect,
} from "../../api/types";

export type BusyAction =
  | "analyze_frames"
  | "cover"
  | "nfo"
  | "plan"
  | "execute"
  | "scan"
  | "batch_generate"
  | "batch_execute"
  | null;

export interface BatchDraftStatus {
  path: string;
  filename: string;
  draft: LocalMetadataDraft;
  coverSettings: CoverEditorSettings;
  status: BatchDraftState;
}

export type BatchDraftState = "drafted";

export type BatchOutputState =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "executing"
  | "executed"
  | "execute_failed"
  | "cancelled";

export type BatchOutputLogTone =
  | "active"
  | "success"
  | "warning"
  | "danger"
  | "neutral";

export interface BatchOutputLog {
  tone: BatchOutputLogTone;
  message: string;
}

export interface BatchOutputItem {
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

export interface CoverEditorSettings {
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
  allowSimilarFrameFallback: boolean;
  similarFrameFallbackThreshold: number;
}

export interface BatchCoverStyleSettings extends CoverEditorSettings {
  randomTitleFormat: boolean;
}

export interface BatchRunOptions {
  destinationRoot: string;
  mode: OrganizationMode;
  folderTemplates: string[];
  filenameTemplate: string;
  extraBackdropCount: number;
  frameCount: number;
}

export type BatchOutputFilter =
  | "all"
  | "attention"
  | "ready"
  | "running"
  | "done";
