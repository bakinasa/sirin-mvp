import { useAuthStore } from "../store/auth";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isForm && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export type Project = {
  id: string;
  title: string;
  client_name: string;
  profession: string;
  audience: string;
  delivery_format: string;
  expected_duration: string;
  constraints: string;
  source_materials: string;
  status: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
};

export type PipelineStep = {
  id: string;
  project_id: string;
  step_type: string;
  order_index: number;
  status: string;
  current_artifact_id: string | null;
  approved_artifact_id: string | null;
};

export type Artifact = {
  id: string;
  project_id: string;
  step_type: string;
  content: unknown;
  format: string;
  version: number;
  status: string;
  approved_by: string | null;
  approved_at: string | null;
  change_type?: string;
  change_summary?: string;
  frozen?: boolean;
  parent_artifact_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type Brief = {
  id: string;
  project_id: string;
  content_json: Record<string, string>;
  version: number;
  status: string;
  updated_at: string;
};

export type ProjectSource = {
  id: string;
  project_id: string;
  title: string;
  source_type: string;
  file_path: string;
  mime_type: string;
  parse_status: string;
  parse_error: string;
  summary_short_json: unknown;
  summary_structured_json: unknown;
  important_chunks_json: unknown;
  summary_progress?: {
    status?: string;
    part_done?: number;
    part_total?: number;
    percent?: number;
    message?: string;
  };
  created_at: string;
  updated_at: string;
  has_parsed_text: boolean;
  parsed_text?: string;
  chunks?: { id: string; chunk_index: number; page_ref: string; text: string }[];
};

export type DocItem = {
  id: string;
  title?: string;
  status?: string;
  [key: string]: unknown;
};

export type DocSection = {
  id: string;
  title: string;
  items: DocItem[];
};

export type BlockDocument = {
  sections?: DocSection[];
  [key: string]: unknown;
};

export type ArtifactPatch = {
  id: string;
  project_id: string;
  stage_type: string;
  artifact_id?: string | null;
  scope: string;
  target_id: string;
  instruction: string;
  patch_json: unknown;
  status: string;
  created_at: string;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: string;
  body: string;
  applied_patch_id?: string | null;
  created_at: string;
};

export type ChatSession = {
  id: string;
  project_id: string;
  stage_type: string;
  mode: string;
  summary_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
};

export type CommentThread = {
  id: string;
  project_id: string;
  stage_type: string;
  artifact_id?: string | null;
  target_type: string;
  target_id: string;
  status: string;
  created_at: string;
  messages: {
    id: string;
    body: string;
    message_type: string;
    decision: string;
    created_at: string;
  }[];
};

export const STEP_LABELS: Record<string, string> = {
  brief: "Brief",
  profession_map: "Карта профессии",
  scenario_plan: "Сценарий и съёмка",
  export: "Экспорт",
  source_summary: "Выжимка файлов",
  chat_ask: "Чат · вопрос",
  chat_local_edit: "Чат · правка блока/раздела",
  chat_global_edit: "Чат · правка всего",
  draft_tz: "Первичное ТЗ",
  expert_feedback: "Экспертный фидбек",
  expert_synthesis: "Сведение фидбека",
  final_tz: "Итоговое ТЗ",
  scene_breakdown: "Сцены и кадры",
  production_planning: "Production",
  storyboard: "Раскадровка",
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  ai_generated: "AI Generated",
  under_review: "Under Review",
  needs_revision: "Needs Revision",
  approved: "Approved",
  locked: "Locked",
  outdated: "Outdated",
  proposed: "Proposed",
  accepted: "Accepted",
  rejected: "Rejected",
  edited: "Edited",
};

export function statusColor(status: string): string {
  switch (status) {
    case "accepted":
    case "approved":
    case "locked":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200";
    case "ai_generated":
    case "under_review":
      return "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200";
    case "needs_revision":
    case "outdated":
      return "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100";
    default:
      return "bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-200";
  }
}

export type Provider = {
  id: string;
  name: string;
  type: string;
  base_url: string;
  capabilities_json: Record<string, unknown>;
  is_active: boolean;
};

export type Model = {
  id: string;
  provider_id: string;
  model_id: string;
  label: string;
  is_free: boolean;
  input_price?: number | null;
  output_price?: number | null;
  context_window?: number | null;
  capabilities_json?: Record<string, unknown>;
  is_enabled?: boolean;
  tags?: unknown[];
  provider_name?: string | null;
};

export type AddProviderModelPayload = {
  model_id: string;
  label: string;
  is_free: boolean;
  input_price?: number | null;
  output_price?: number | null;
  context_window?: number | null;
  capabilities_json?: Record<string, unknown>;
  tags?: string[];
};
