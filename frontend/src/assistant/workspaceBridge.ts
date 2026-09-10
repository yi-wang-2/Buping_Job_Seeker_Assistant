import { useEffect } from "react";

export interface AssistantProposal {
  id: string;
  proposal_type: string;
  target_ref: string;
  target_version: string;
  status: string;
  payload: {
    original_text?: string;
    replacement_text?: string;
    mode?: string;
    base_artifact_hash?: string;
    original_text_hash?: string;
    [key: string]: unknown;
  };
}

export interface WorkspaceSnapshot {
  selected_text?: string;
  surrounding_context?: string;
  language?: "zh" | "en";
  version?: string;
  summary?: string;
  job_description?: string;
  interview_report?: string;
  coding_task?: Record<string, unknown>;
  coding_code?: string;
  job_preferences?: Record<string, unknown>;
  job_radar_stats?: {
    total: number;
    companies: number;
    favorites: number;
    by_scene: Record<string, number>;
    last_sync_at?: string | null;
  };
  job_results_meta?: {
    matching_results: number;
    sample_size: number;
    is_sample: boolean;
    scene: string;
  };
  job_results?: Array<Record<string, unknown>>;
  resume_generation_options?: { generation_mode: "new" | "partial"; target_pages: 1 | 2; style_name: string };
  interview_generation_options?: { interview_type: string; question_count: number };
  resume_artifact?: {
    id: string;
    version: string;
    content_format: "html" | "text";
    content: string;
    source: "editor_unsaved" | "preview";
    is_dirty: boolean;
  };
}

export interface WorkspaceContextDescriptor {
  id: string;
  label: string;
  description?: string;
  snapshotKeys: Array<keyof WorkspaceSnapshot>;
  selectedObjects?: string[];
  defaultAttached?: boolean;
}

export interface WorkspaceBridge {
  page: string;
  workspaceObjectId: string;
  selectedObjects: string[];
  getContextSnapshot: () => Promise<WorkspaceSnapshot> | WorkspaceSnapshot;
  describeContexts?: (snapshot: WorkspaceSnapshot) => WorkspaceContextDescriptor[];
  applyProposal?: (proposal: AssistantProposal) => Promise<void> | void;
  undoProposal?: (proposal: AssistantProposal) => Promise<void> | void;
}

let activeBridge: WorkspaceBridge | null = null;

export function getWorkspaceBridge(): WorkspaceBridge | null {
  return activeBridge;
}

export function useWorkspaceBridgeRegistration(bridge: WorkspaceBridge): void {
  useEffect(() => {
    activeBridge = bridge;
    window.dispatchEvent(new CustomEvent("buping:workspace-context-changed"));
    return () => {
      if (activeBridge === bridge) {
        activeBridge = null;
        window.dispatchEvent(new CustomEvent("buping:workspace-context-changed"));
      }
    };
  }, [bridge]);
}
