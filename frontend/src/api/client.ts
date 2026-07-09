import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 300000, // 5 min for LLM calls
});

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

// ---- Resume ----
export async function getStyles(): Promise<Record<string, { file: string; author: string }>> {
  const { data } = await api.get("/resume/styles");
  return data;
}

export async function generateResume(params: {
  api_key?: string;
  model_type?: string;
  base_url?: string;
  llm_protocol?: string;
  style_name?: string;
  job_description?: string;
  resume_language?: string;
  system_language?: string;
}): Promise<{ path: string; filename: string; html_filename?: string; html_path?: string; status: string }> {
  const { data } = await api.post("/resume/generate", params);
  return data;
}

export async function previewResume(params: {
  style_name?: string;
  resume_language?: string;
}): Promise<{ html: string; style: string; language: string }> {
  const { data } = await api.post("/resume/preview", params);
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
  base_url?: string;
  job_description?: string;
  interview_type?: string;
  question_count?: number;
  resume_language?: string;
}): Promise<{ report: string; file_path: string; status: string }> {
  const { data } = await api.post("/interview/prep", params);
  return data;
}

export async function startMockInterview(params: {
  api_key?: string;
  model_type?: string;
  base_url?: string;
  resume_text?: string;
  job_description?: string;
  company_name?: string;
  company_industry?: string;
  job_title?: string;
  interview_type?: string;
  interview_style?: string;
}): Promise<{ history: Array<{ role: string; content: string }>; session_id: string | null; status: string }> {
  const { data } = await api.post("/interview/mock/start", params);
  return data;
}

export async function submitMockAnswer(params: {
  session_id: string;
  user_message: string;
  history: Array<{ role: string; content: string }>;
}): Promise<{ history: Array<{ role: string; content: string }>; session_id: string | null; status: string }> {
  const { data } = await api.post("/interview/mock/submit", params);
  return data;
}

export async function endMockInterview(params: {
  session_id: string;
  history: Array<{ role: string; content: string }>;
}): Promise<{ evaluation: string; file_path: string; status: string }> {
  const { data } = await api.post("/interview/mock/end", params);
  return data;
}

// ---- Settings ----
export async function getSettings(): Promise<{
  llm_api_key: string;
  llm_model_type: string;
  llm_base_url: string;
  llm_protocol: string;
  resume_language: string;
  system_language: string;
}> {
  const { data } = await api.get("/settings");
  return data;
}

export interface UploadResumeResponse {
  status: string;
  filename: string;
  ext: string;
  yaml_content: string;
  message: string;
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
    baseUrl?: string;
    llmProtocol?: string;
  },
): Promise<UploadResumeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_lang", targetLang);
  if (options?.apiKey) formData.append("api_key", options.apiKey);
  if (options?.modelType) formData.append("model_type", options.modelType);
  if (options?.baseUrl) formData.append("base_url", options.baseUrl);
  if (options?.llmProtocol) formData.append("llm_protocol", options.llmProtocol);
  const { data } = await api.post("/settings/upload-resume", formData, {
    headers: {"Content-Type": "multipart/form-data"},
    timeout: 180000, // 3 min for LLM extraction
  });
  return data;
}

export async function saveSettings(params: {
  llm_api_key?: string;
  llm_model_type?: string;
  llm_base_url?: string;
  llm_protocol?: string;
  resume_language?: string;
  system_language?: string;
}): Promise<{ status: string; message: string }> {
  const { data } = await api.put("/settings", params);
  return data;
}

export async function getResumeContent(language: string = "zh"): Promise<{ content: string; language: string }> {
  const { data } = await api.get("/settings/resume-content", { params: { language } });
  return data;
}

export async function saveResumeContent(params: {
  content: string;
  language: string;
}): Promise<{ status: string; message: string }> {
  const { data } = await api.put("/settings/resume-content", params);
  return data;
}

// ---- History ----
export async function getHistory(): Promise<{
  files: Array<{ name: string; path: string; size: number; modified: string }>;
  count: number;
}> {
  const { data } = await api.get("/history");
  return data;
}

export async function clearHistory(): Promise<{ status: string; message: string; cleared: number }> {
  const { data } = await api.delete("/history");
  return data;
}
