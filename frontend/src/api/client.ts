import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 300000, // 5 min for LLM calls
});

const API_KEY_SESSION_KEY = "buping_llm_api_key";
const IS_CLOUD = import.meta.env.VITE_DEPLOYMENT_MODE === "cloud";
const IS_PUBLIC = import.meta.env.VITE_DEPLOYMENT_MODE === "public";
const PUBLIC_SETTINGS_SESSION_KEY = "buping_public_settings";
const PUBLIC_METRICS_SESSION_KEY = "buping_public_ai_metrics";
const PUBLIC_JOB_SESSION_KEY = "buping_public_job_tracker";
const PUBLIC_HISTORY_SESSION_KEY = "buping_public_resume_history";
const publicResumeKey = (language: string) => `buping_public_resume_${language === "en" ? "en" : "zh"}`;

export interface AIMetrics {
  period_days: number;
  summary: {
    calls: number; successful_calls: number; errors: number; success_rate: number;
    input_tokens: number; output_tokens: number; total_tokens: number; retries: number;
    avg_latency_ms: number; p95_latency_ms: number; cache_hits: number; cache_entries: number;
    cache_hit_rate: number; memory_items: number; context_original_tokens: number;
    context_final_tokens: number; context_saved_tokens: number; context_compression_rate: number;
    compressed_items: number; dropped_items: number;
  };
  by_skill: Array<{ skill: string; calls: number; tokens: number; errors: number; avg_latency_ms: number }>;
  by_model: Array<{ model: string; calls: number; tokens: number }>;
  timeline: Array<{ date: string; calls: number; tokens: number; errors: number }>;
  recent: Array<Record<string, any>>;
}

type PublicMetric = { timestamp: string; skill: string; status: "success" | "error"; latency_ms: number };

function publicMetrics(): PublicMetric[] {
  try { return JSON.parse(window.sessionStorage.getItem(PUBLIC_METRICS_SESSION_KEY) || "[]"); }
  catch { return []; }
}

function recordPublicMetric(config: any, status: "success" | "error") {
  if (!IS_PUBLIC || String(config?.method || "get").toLowerCase() === "get") return;
  const url = String(config?.url || "");
  if (!/^\/(resume|interview|ai|settings\/models|settings\/upload-resume)/.test(url)) return;
  const started = Number(config?.__bupingStartedAt || Date.now());
  const records = publicMetrics();
  records.push({
    timestamp: new Date().toISOString(),
    skill: url.split("?")[0].replace(/^\//, ""),
    status,
    latency_ms: Math.max(0, Date.now() - started),
  });
  window.sessionStorage.setItem(PUBLIC_METRICS_SESSION_KEY, JSON.stringify(records.slice(-100)));
}

export async function getAIMetrics(days = 30): Promise<AIMetrics> {
  if (IS_PUBLIC) {
    const cutoff = Date.now() - days * 86400000;
    const rows = publicMetrics().filter((row) => Date.parse(row.timestamp) >= cutoff);
    const successful = rows.filter((row) => row.status === "success").length;
    const latencies = rows.map((row) => row.latency_ms).sort((a, b) => a - b);
    const average = rows.length ? Math.round(latencies.reduce((a, b) => a + b, 0) / rows.length) : 0;
    const grouped = new Map<string, PublicMetric[]>();
    rows.forEach((row) => grouped.set(row.skill, [...(grouped.get(row.skill) || []), row]));
    return {
      period_days: days,
      summary: {
        calls: rows.length, successful_calls: successful, errors: rows.length - successful,
        success_rate: rows.length ? Math.round(successful / rows.length * 100) : 0,
        input_tokens: 0, output_tokens: 0, total_tokens: 0, retries: 0,
        avg_latency_ms: average,
        p95_latency_ms: latencies.length ? latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * .95))] : 0,
        cache_hits: 0, cache_entries: 0, cache_hit_rate: 0, memory_items: 0,
        context_original_tokens: 0, context_final_tokens: 0, context_saved_tokens: 0,
        context_compression_rate: 0, compressed_items: 0, dropped_items: 0,
      },
      by_skill: Array.from(grouped, ([skill, items]) => ({
        skill, calls: items.length, tokens: 0,
        errors: items.filter((item) => item.status === "error").length,
        avg_latency_ms: Math.round(items.reduce((sum, item) => sum + item.latency_ms, 0) / items.length),
      })),
      by_model: [], timeline: [], recent: rows.slice().reverse().map((row, index) => ({
        ...row, trace_id: `browser-${index}`, model: "browser session", usage: { total_tokens: 0 },
      })),
    };
  }
  const { data } = await api.get("/ai-metrics", { params: { days } });
  return data;
}

export async function getCurrentUser(): Promise<{ authenticated: boolean; user_id: string }> {
  const { data } = await api.get("/me");
  return data;
}

// Retry on connection failures (e.g. backend not yet up after
// `start-dev.bat` launches both servers). Chrome driver init + model
// imports can take 3-6 seconds, so we use exponential backoff up to
// ~10 seconds total. The component-level "retry" button provides
// a manual fallback if this still fails.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error?.config;
    const isNetworkError =
      error?.code === "ERR_NETWORK" ||
      error?.code === "ECONNREFUSED" ||
      error?.message?.includes("Network Error") ||
      error?.message?.includes("ECONNREFUSED");
    // Allow up to 4 retries with exponential backoff: 800ms, 1.6s, 3.2s, 6.4s
    // (~12 seconds total). Reset the counter for fresh requests.
    const attempt = (config?.__bupingRetryCount || 0) + 1;
    const MAX_RETRIES = 4;
    const BACKOFFS_MS = [800, 1600, 3200, 6400];

    if (isNetworkError && attempt <= MAX_RETRIES && config) {
      config.__bupingRetryCount = attempt;
      const wait = BACKOFFS_MS[attempt - 1] || 6400;
      await new Promise((resolve) => setTimeout(resolve, wait));
      return api.request(config);
    }

    return Promise.reject(error);
  },
);

api.interceptors.request.use((config: any) => {
  if (IS_PUBLIC) config.__bupingStartedAt = Date.now();
  return config;
});
api.interceptors.response.use(
  (response) => { recordPublicMetric(response.config, "success"); return response; },
  (error) => { recordPublicMetric(error?.config, "error"); return Promise.reject(error); },
);

// ---- Resume ----
export async function getStyles(): Promise<Record<string, { file: string; author: string }>> {
  const { data } = await api.get("/resume/styles");
  return data;
}

export async function generateResume(params: {
  api_key?: string;
  model_type?: string;
  model_name?: string;
  base_url?: string;
  llm_protocol?: string;
  style_name?: string;
  job_description?: string;
  resume_language?: string;
  system_language?: string;
  resume_content?: string;
  generation_mode?: "new" | "partial";
  base_html?: string;
  regenerate_targets?: string[];
  target_pages?: 1 | 2;
  request_id?: string;
}): Promise<{
  path: string;
  filename: string;
  html_filename?: string;
  html_path?: string;
  status: string;
  generation_mode?: "new" | "partial";
  regenerated_targets?: string[];
  target_pages?: 1 | 2;
  actual_pages?: number;
  layout_warnings?: string[];
  layout_scale?: number;
  request_id?: string;
}> {
  const payload = IS_PUBLIC ? {
    ...params,
    resume_content: params.resume_content || window.sessionStorage.getItem(publicResumeKey(params.resume_language || "zh")) || "",
  } : params;
  const { data } = await api.post("/resume/generate", payload);
  if (IS_PUBLIC) {
    const files = JSON.parse(window.sessionStorage.getItem(PUBLIC_HISTORY_SESSION_KEY) || "[]");
    files.unshift({ name: data.filename, html_filename: data.html_filename || "", path: data.path, size: 0, modified: new Date().toLocaleString() });
    window.sessionStorage.setItem(PUBLIC_HISTORY_SESSION_KEY, JSON.stringify(files.slice(0, 30)));
  }
  return data;
}

export interface ResumeGenerationProgress {
  progress: number;
  stage: string;
  detail: string;
  status: "running" | "completed" | "failed";
  events: Array<{ progress: number; stage: string; detail: string }>;
}

export async function getResumeGenerationProgress(requestId: string): Promise<ResumeGenerationProgress> {
  const { data } = await api.get(`/resume/generate/progress/${encodeURIComponent(requestId)}`);
  return data;
}

export async function previewResume(params: {
  style_name?: string;
  resume_language?: string;
  resume_content?: string;
}): Promise<{ html: string; style: string; language: string }> {
  const payload = IS_PUBLIC ? {
    ...params,
    resume_content: params.resume_content || window.sessionStorage.getItem(publicResumeKey(params.resume_language || "zh")) || "",
  } : params;
  const { data } = await api.post("/resume/preview", payload);
  return data;
}

export function getPreviewPageUrl(style: string, language: string): string {
  const params = new URLSearchParams({ style, language });
  return `/api/resume/preview/render?${params.toString()}`;
}

export function getDownloadUrl(filename: string): string {
  return `/api/resume/download/${encodeURIComponent(filename)}`;
}

// Preview a previously-saved resume by HTML filename
export async function previewSavedResume(htmlFilename: string): Promise<{ html: string }> {
  const { data } = await api.get(`/resume/preview-saved/${encodeURIComponent(htmlFilename)}`);
  return data;
}

// ---- Save edited HTML (from WYSIWYG editor) ----
export interface SaveEditedResponse {
  status: string;
  pdf_filename: string;
  html_filename: string;
  pdf_size: number;
  message: string;
}

export async function saveEditedResume(
  html: string,
  filenameBase: string = "resume_edited",
): Promise<SaveEditedResponse> {
  const { data } = await api.post("/resume/save-edited", {
    html,
    filename_base: filenameBase,
  }, {
    timeout: 120000, // 2 min for Chrome PDF rendering
  });
  if (IS_PUBLIC) {
    const files = JSON.parse(window.sessionStorage.getItem(PUBLIC_HISTORY_SESSION_KEY) || "[]");
    files.unshift({ name: data.pdf_filename, html_filename: data.html_filename, path: "browser session", size: data.pdf_size, modified: new Date().toLocaleString() });
    window.sessionStorage.setItem(PUBLIC_HISTORY_SESSION_KEY, JSON.stringify(files.slice(0, 30)));
  }
  return data;
}

// ---- AI Rewrite (Roadmap §1) ----
export type RewriteMode = "more_quantified" | "more_professional" | "more_concise" | "fix_grammar";

export interface RewriteModeInfo {
  id: RewriteMode;
  icon: string;
  label_zh: string;
  label_en: string;
  desc_zh: string;
  desc_en: string;
}

export async function getRewriteModes(): Promise<{ modes: RewriteModeInfo[] }> {
  const { data } = await api.get("/resume/rewrite/modes");
  return data;
}

export interface RewriteRequest {
  text: string;
  mode: RewriteMode;
  context?: string;
  target_language?: "zh" | "en";
  api_key?: string;
  model_type?: string;
  model_name?: string;
  base_url?: string;
  llm_protocol?: string;
}

export interface RewriteResponse {
  status: string;
  original: string;
  rewritten: string;
  mode: RewriteMode;
  message: string;
}

export async function rewriteText(params: RewriteRequest): Promise<RewriteResponse> {
  const { data } = await api.post("/resume/rewrite", params, {
    timeout: 120000, // 2 min for LLM rewrite
  });
  return data;
}

// ---- Interview ----
export async function generateInterviewPrep(params: {
  api_key?: string;
  model_type?: string;
  model_name?: string;
  base_url?: string;
  job_description?: string;
  interview_type?: string;
  question_count?: number;
  resume_language?: string;
}): Promise<{ report: string; file_path: string; md_filename: string; pdf_filename: string; status: string }> {
  const { data } = await api.post("/interview/prep", params);
  return data;
}

export function getInterviewPrepDownloadUrl(filename: string): string {
  return `/api/interview/prep/download/${encodeURIComponent(filename)}`;
}

export async function startMockInterview(params: {
  api_key?: string;
  model_type?: string;
  model_name?: string;
  base_url?: string;
  resume_text?: string;
  job_description?: string;
  company_name?: string;
  company_industry?: string;
  job_title?: string;
  interview_type?: string;
  interview_style?: string;
}): Promise<{ history: Array<{ role: string; content: string }>; session_id: string | null; status: string }> {
  let payload = params;
  if ((IS_CLOUD || IS_PUBLIC) && !params.api_key) {
    const settings = await getSettings();
    payload = {
      ...params,
      api_key: settings.llm_api_key,
      model_type: settings.llm_model_type,
      model_name: settings.llm_model,
      base_url: settings.llm_base_url,
    };
  }
  const { data } = await api.post("/interview/mock/start", payload);
  return data;
}

export async function submitMockAnswer(params: {
  session_id: string;
  user_message: string;
  history: Array<{ role: string; content: string }>;
  context_window?: number;
}): Promise<{ history: Array<{ role: string; content: string }>; session_id: string | null; status: string }> {
  const { data } = await api.post("/interview/mock/submit", params);
  return data;
}

export function getMockInterviewDownloadUrl(filename: string): string {
  return `/api/interview/mock/download/${encodeURIComponent(filename)}`;
}

export async function getMockInterviewTTSVoices(): Promise<{
  kokoro: Array<{ id: string; label: string }>;
}> {
  const { data } = await api.get("/interview/mock/tts/voices");
  return data;
}

export async function getMemorySettings(): Promise<{ memory_enabled: boolean; cache_enabled: boolean }> {
  const { data } = await api.get("/memory/settings");
  return data;
}

export async function saveMemorySettings(settings: {
  memory_enabled: boolean;
  cache_enabled: boolean;
}): Promise<{ memory_enabled: boolean; cache_enabled: boolean }> {
  const { data } = await api.put("/memory/settings", settings);
  return data;
}

export async function clearAIMemory(): Promise<{ deleted: number }> {
  const { data } = await api.delete("/memory");
  return data;
}

export async function synthesizeMockInterviewSpeech(params: {
  text: string;
  provider?: string;
  voice?: string;
  rate?: string;
  api_key?: string;
}, signal?: AbortSignal): Promise<Blob> {
  const request = {
    ...params,
    api_key: params.api_key || window.sessionStorage.getItem(API_KEY_SESSION_KEY) || "",
  };
  const { data } = await api.post("/interview/mock/tts", request, {
    responseType: "blob",
    timeout: 120000,
    signal,
  });
  return data;
}

export async function streamMockInterviewSpeech(params: {
  text: string;
  provider?: string;
  voice?: string;
  rate?: string;
  api_key?: string;
}, signal?: AbortSignal): Promise<Response> {
  const request = {
    ...params,
    api_key: params.api_key || window.sessionStorage.getItem(API_KEY_SESSION_KEY) || "",
  };
  const response = await fetch("/api/interview/mock/tts/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `TTS stream failed with ${response.status}`);
  }
  if (!response.body) {
    throw new Error("TTS stream returned empty body");
  }
  return response;
}

export async function endMockInterview(params: {
  session_id: string;
  history: Array<{ role: string; content: string }>;
}): Promise<{ evaluation: string; file_path: string; pdf_filename?: string; status: string }> {
  const { data } = await api.post("/interview/mock/end", params);
  return data;
}

// ---- Settings ----
export async function getSettings(): Promise<{
  llm_api_key: string;
  llm_model_type: string;
  llm_model: string;
  llm_base_url: string;
  llm_protocol: string;
  resume_language: string;
  system_language: string;
}> {
  const { data } = await api.get("/settings");
  if (IS_CLOUD || IS_PUBLIC) data.llm_api_key = window.sessionStorage.getItem(API_KEY_SESSION_KEY) || "";
  if (IS_PUBLIC) {
    const saved = window.sessionStorage.getItem(PUBLIC_SETTINGS_SESSION_KEY);
    if (saved) Object.assign(data, JSON.parse(saved));
    data.llm_api_key = window.sessionStorage.getItem(API_KEY_SESSION_KEY) || "";
  }
  return data;
}

export interface UploadResumeResponse {
  status: string;
  filename: string;
  ext: string;
  yaml_content: string;
  message: string;
  validation?: ResumeValidation;
  parse_diagnostics?: {
    llm_attempted?: boolean;
    llm_call_success?: boolean;
    llm_yaml_parse_success?: boolean;
    used_fallback?: boolean;
    fallback_reason?: string;
    extracted_text_chars?: number;
    llm_raw_chars?: number;
    llm_yaml_candidate_chars?: number;
    llm_yaml_error?: string;
  };
}

export async function uploadResume(
  file: File,
  targetLang: string = "en",
  options?: {
    apiKey?: string;
    modelType?: string;
    modelName?: string;
    baseUrl?: string;
    llmProtocol?: string;
  },
): Promise<UploadResumeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_lang", targetLang);
  if (options?.apiKey) formData.append("api_key", options.apiKey);
  if (options?.modelType) formData.append("model_type", options.modelType);
  if (options?.modelName) formData.append("model_name", options.modelName);
  if (options?.baseUrl) formData.append("base_url", options.baseUrl);
  if (options?.llmProtocol) formData.append("llm_protocol", options.llmProtocol);
  const { data } = await api.post("/settings/upload-resume", formData, {
    headers: {"Content-Type": "multipart/form-data"},
    timeout: 180000, // 3 min for LLM extraction
  });
  return data;
}

export async function getResumePhotoStatus(): Promise<{ uploaded: boolean; filename: string }> {
  const { data } = await api.get("/settings/resume-photo/status");
  return data;
}

export async function uploadResumePhoto(file: File): Promise<{ status: string; filename: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post("/settings/resume-photo", formData, {
    headers: {"Content-Type": "multipart/form-data"},
    timeout: 30000,
  });
  return data;
}

export async function deleteResumePhoto(): Promise<{ status: string; deleted: boolean }> {
  const { data } = await api.delete("/settings/resume-photo");
  return data;
}

export function getResumePhotoUrl(cacheKey = ""): string {
  return `/api/settings/resume-photo${cacheKey ? `?v=${encodeURIComponent(cacheKey)}` : ""}`;
}

export async function saveSettings(params: {
  llm_api_key?: string;
  llm_model_type?: string;
  llm_model?: string;
  llm_base_url?: string;
  llm_protocol?: string;
  resume_language?: string;
  system_language?: string;
}): Promise<{ status: string; message: string }> {
  if (!IS_CLOUD && !IS_PUBLIC) {
    const { data } = await api.put("/settings", params);
    return data;
  }
  if (params.llm_api_key) window.sessionStorage.setItem(API_KEY_SESSION_KEY, params.llm_api_key);
  else window.sessionStorage.removeItem(API_KEY_SESSION_KEY);
  const { llm_api_key: _apiKey, ...cloudSettings } = params;
  if (IS_PUBLIC) {
    window.sessionStorage.setItem(PUBLIC_SETTINGS_SESSION_KEY, JSON.stringify(cloudSettings));
    return { status: "success", message: "Settings saved in this browser session only" };
  }
  const { data } = await api.put("/settings", cloudSettings);
  return data;
}

export interface NotificationSettings {
  email_enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_from: string;
  smtp_to: string;
  smtp_security: "ssl" | "starttls" | "none";
  wechat_enabled: boolean;
  smtp_password_configured: boolean;
  serverchan_sendkey_configured: boolean;
}

export async function getNotificationSettings(): Promise<NotificationSettings> {
  const { data } = await api.get("/settings/notifications");
  return data;
}

export async function saveNotificationSettings(settings: NotificationSettings & {
  smtp_password?: string;
  serverchan_sendkey?: string;
}): Promise<{ status: string; settings: NotificationSettings }> {
  const { data } = await api.put("/settings/notifications", settings);
  return data;
}

export async function testNotifications(): Promise<{
  status: string; sent: number; results: Array<{ channel: string; status: string; error?: string }>;
}> {
  const { data } = await api.post("/settings/notifications/test", {}, { timeout: 30000 });
  return data;
}

export interface ResumeValidationItem {
  path: string;
  message: string;
}

export interface ResumeValidation {
  valid: boolean;
  errors: ResumeValidationItem[];
  warnings: ResumeValidationItem[];
}

export async function discoverModels(params: {
  llm_api_key: string;
  llm_base_url: string;
  llm_protocol: string;
}): Promise<{ models: string[] }> {
  const { data } = await api.post("/settings/models", params, { timeout: 15000 });
  return data;
}

export async function getResumeContent(language: string = "zh"): Promise<{ content: string; language: string }> {
  if (IS_PUBLIC) {
    const saved = window.sessionStorage.getItem(publicResumeKey(language));
    if (saved !== null) return { content: saved, language };
    const { data } = await api.get("/settings/resume-content", { params: { language } });
    window.sessionStorage.setItem(publicResumeKey(language), data.content || "");
    return data;
  }
  const { data } = await api.get("/settings/resume-content", { params: { language } });
  return data;
}

export async function saveResumeContent(params: {
  content: string;
  language: string;
}): Promise<{ status: string; message: string; validation?: ResumeValidation }> {
  if (IS_PUBLIC) {
    window.sessionStorage.setItem(publicResumeKey(params.language), params.content);
    return { status: "success", message: "Resume saved in this browser session only" };
  }
  const { data } = await api.put("/settings/resume-content", params);
  return data;
}

// ---- History ----
export async function getHistory(): Promise<{
  files: Array<{ name: string; path: string; size: number; modified: string }>;
  count: number;
}> {
  if (IS_PUBLIC) {
    const files = JSON.parse(window.sessionStorage.getItem(PUBLIC_HISTORY_SESSION_KEY) || "[]");
    return { files, count: files.length };
  }
  const { data } = await api.get("/history");
  return data;
}

export async function clearHistory(): Promise<{ status: string; message: string; cleared: number }> {
  if (IS_PUBLIC) {
    const files = JSON.parse(window.sessionStorage.getItem(PUBLIC_HISTORY_SESSION_KEY) || "[]");
    window.sessionStorage.removeItem(PUBLIC_HISTORY_SESSION_KEY);
    return { status: "success", message: "Browser session history cleared", cleared: files.length };
  }
  const { data } = await api.delete("/history");
  return data;
}

// ---- Job Tracker ----

export interface JobEntry {
  id: number;
  company: string;
  role: string;
  base: string;
  remark: string;
  link: string;
  status: string;
  icon: string;
  notes: string;
  followup_enabled?: boolean;
  followup_ai_enabled?: boolean;
  followup_platform?: string;
  followup_url?: string;
  followup_state?: string;
  last_checked_at?: string;
  last_raw_status?: string;
  last_check_message?: string;
  last_parser?: string;
  last_llm_confidence?: number | null;
  last_llm_tokens?: number;
  last_notification?: { sent: number; results: Array<{ channel: string; status: string; error?: string }> };
  status_history?: Array<{ status: string; raw_status: string; checked_at: string; evidence_url: string; source: string }>;
}

export async function getJobTrackerRecords(): Promise<{ records: JobEntry[]; count: number }> {
  if (IS_PUBLIC) {
    const records = JSON.parse(window.sessionStorage.getItem(PUBLIC_JOB_SESSION_KEY) || "[]") as JobEntry[];
    return { records, count: records.length };
  }
  const { data } = await api.get("/job-tracker");
  return data;
}

export async function saveJobTrackerRecords(
  records: JobEntry[],
): Promise<{ status: string; saved: number; path: string }> {
  if (IS_PUBLIC) {
    window.sessionStorage.setItem(PUBLIC_JOB_SESSION_KEY, JSON.stringify(records));
    return { status: "ok", saved: records.length, path: "browser session" };
  }
  const { data } = await api.put("/job-tracker", { records });
  return data;
}

export async function getJobTrackerStats(): Promise<{
  total: number;
  interviewing: number;
  offers: number;
  rejected: number;
  company_counts: Record<string, number>;
}> {
  if (IS_PUBLIC) {
    const { records } = await getJobTrackerRecords();
    return {
      total: records.length,
      interviewing: records.filter((r) => r.status.includes("面") && !r.status.includes("拒")).length,
      offers: records.filter((r) => r.status.toLowerCase() === "offer").length,
      rejected: records.filter((r) => r.status.includes("拒")).length,
      company_counts: records.reduce<Record<string, number>>((out, row) => {
        if (row.company) out[row.company] = (out[row.company] || 0) + 1;
        return out;
      }, {}),
    };
  }
  const { data } = await api.get("/job-tracker/stats");
  return data;
}

export async function connectJobFollowup(platform: string, portalUrl: string): Promise<{ status: string; platform: string; message: string }> {
  const { data } = await api.post("/job-tracker/followup/connect", { platform, portal_url: portalUrl }, { timeout: 120000 });
  return data;
}

export async function completeJobFollowupLogin(platform: string): Promise<{ status: string; platform: string; message: string }> {
  const { data } = await api.post("/job-tracker/followup/complete", { platform });
  return data;
}

export async function checkJobFollowup(entryId: number): Promise<{ status: string; record: JobEntry; result: string; message: string }> {
  const { data } = await api.post(`/job-tracker/${entryId}/followup/check`, {}, { timeout: 120000 });
  return data;
}

export async function checkAllJobFollowups(): Promise<{ status: string; checked: number; results: Array<Record<string, unknown>> }> {
  const { data } = await api.post("/job-tracker/followup/check-all", {}, { timeout: 300000 });
  return data;
}

// ---- Job Radar ----

export interface JobRecommendation {
  id: string;
  company: string;
  role: string;
  location: string;
  industry: string;
  recruitment_type: string;
  link: string;
  referral: string;
  deadline: string;
  description: string;
  source_name: string;
  source_url: string;
  first_seen_at: string;
  last_seen_at: string;
  updated_at: string;
  score: number;
  reasons: string[];
  matched_skills: string[];
  missing_skills: string[];
  hard_risks: string[];
  breakdown: Record<string, number>;
  company_type: string;
  match_level: "高匹配" | "中匹配" | "低匹配";
  recruitment_tags: string[];
  favorite: boolean;
  not_interested: boolean;
  applied: boolean;
}

export interface JobRadarStats {
  total: number;
  companies: number;
  favorites: number;
  schedule: { source_url: string; auto_sync: boolean; auto_sync_time: string };
  last_sync: null | {
    imported: number;
    created: number;
    updated: number;
    unchanged: number;
    created_at: string;
  };
}

export interface JobPreferences {
  target_roles: string[];
  preferred_locations: string[];
  acceptable_locations: string[];
  excluded_locations: string[];
  recruitment_types: string[];
  industries: string[];
  company_types: string[];
  preferred_keywords: string[];
  excluded_keywords: string[];
  company_blacklist: string[];
  weights: Record<string, number>;
}

export async function syncJobRadarUrl(sourceUrl: string): Promise<{
  status: string; imported: number; created: number; updated: number; unchanged: number; synced_at: string;
}> {
  const { data } = await api.post("/job-radar/sync-url", { source_url: sourceUrl }, { timeout: 180000 });
  return data;
}

export async function importJobRadarFile(file: File, sourceUrl = ""): Promise<{
  status: string; imported: number; created: number; updated: number; unchanged: number; synced_at: string;
}> {
  const form = new FormData();
  form.append("file", file);
  form.append("source_url", sourceUrl);
  const { data } = await api.post("/job-radar/import", form, { timeout: 120000 });
  return data;
}

export async function getJobRadarRecommendations(params: {
  minScore?: number; query?: string; limit?: number; companyType?: string;
  matchLevel?: string; recruitmentType?: string; favoriteOnly?: boolean;
} = {}): Promise<{
  items: JobRecommendation[];
  count: number;
  profile: { preferred_roles: string[]; preferred_locations: string[]; resume_skills: string[] };
}> {
  const { data } = await api.get("/job-radar/recommendations", {
    params: {
      min_score: params.minScore ?? 0, query: params.query ?? "", limit: params.limit ?? 200,
      company_type: params.companyType ?? "", match_level: params.matchLevel ?? "",
      recruitment_type: params.recruitmentType ?? "", favorite_only: params.favoriteOnly ?? false,
    },
  });
  return data;
}

export async function getJobRadarStats(): Promise<JobRadarStats> {
  const { data } = await api.get("/job-radar/stats");
  return data;
}

export async function getJobPreferences(): Promise<JobPreferences> {
  const { data } = await api.get("/job-radar/preferences");
  return data;
}

export async function saveJobPreferences(preferences: JobPreferences): Promise<{ status: string; preferences: JobPreferences }> {
  const { data } = await api.put("/job-radar/preferences", preferences);
  return data;
}

export async function trackRecommendedJob(jobId: string, confirmed?: {
  company: string; role: string; base: string; recruitment_type: string; link: string; notes: string;
}): Promise<{ status: "added" | "exists" | "updated"; record: JobEntry }> {
  const { data } = await api.post(`/job-radar/${encodeURIComponent(jobId)}/track`, confirmed ?? {});
  return data;
}

export async function getDailyJobRecommendations(): Promise<{ items: JobRecommendation[]; count: number; date: string }> {
  const { data } = await api.get("/job-radar/daily");
  return data;
}

export async function updateJobRadarAction(
  jobId: string, action: "favorite" | "not_interested", enabled: boolean,
): Promise<{ status: string; favorite: boolean; not_interested: boolean; applied: boolean }> {
  const { data } = await api.put(`/job-radar/${encodeURIComponent(jobId)}/action`, { action, enabled });
  return data;
}
