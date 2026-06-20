import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 300000, // 5 min for LLM calls
});

// ---- Resume ----
export async function getStyles(): Promise<Record<string, { file: string; author: string }>> {
  const { data } = await api.get("/resume/styles");
  return data;
}

export async function generateResume(params: {
  api_key?: string;
  model_type?: string;
  base_url?: string;
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
}

export async function uploadResume(
  file: File,
  targetLang: string = "en",
  options?: {
    apiKey?: string;
    modelType?: string;
    baseUrl?: string;
  },
): Promise<UploadResumeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_lang", targetLang);
  if (options?.apiKey) formData.append("api_key", options.apiKey);
  if (options?.modelType) formData.append("model_type", options.modelType);
  if (options?.baseUrl) formData.append("base_url", options.baseUrl);
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
