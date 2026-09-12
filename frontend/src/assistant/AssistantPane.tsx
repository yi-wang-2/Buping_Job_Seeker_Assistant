import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Check, FileUp, LoaderCircle, Paperclip, Plus, Send, Sparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  applyAssistantProposal,
  cancelAssistantRun,
  confirmAssistantProposal,
  createAssistantSession,
  dismissAssistantProposal,
  getAssistantRun,
  getAssistantSession,
  getSettings,
  streamAssistantMessage,
  uploadAssistantAttachment,
  undoAssistantProposal,
  type AssistantAttachment,
  type AssistantMessage,
  type AssistantProposal,
} from "../api/client";
import type { Lang } from "../i18n";
import {
  getWorkspaceBridge,
  type WorkspaceContextDescriptor,
  type WorkspaceSnapshot,
} from "./workspaceBridge";
import RunProgress from "./RunProgress";
import type { RuntimeEvent } from "./RunProgress";

interface Props {
  page: string;
  lang: Lang;
}

export default function AssistantPane({ page, lang }: Props) {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [activeRunId, setActiveRunId] = useState("");
  const [proposal, setProposal] = useState<AssistantProposal | null>(null);
  const [error, setError] = useState("");
  const [progressStage, setProgressStage] = useState<"context" | "submitted">("context");
  const [liveEvents, setLiveEvents] = useState<RuntimeEvent[]>([]);
  const [streamingMessage, setStreamingMessage] = useState<AssistantMessage | null>(null);
  const [streamedContent, setStreamedContent] = useState("");
  const [liveStreamActive, setLiveStreamActive] = useState(false);
  const [workspaceContextOptions, setWorkspaceContextOptions] = useState<WorkspaceContextDescriptor[]>([]);
  const [attachments, setAttachments] = useState<AssistantAttachment[]>([]);
  const [attachedContextIds, setAttachedContextIds] = useState<string[]>([]);
  const [contextMenuOpen, setContextMenuOpen] = useState(false);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const shouldFollowOutputRef = useRef(true);
  const explicitlyDetachedRef = useRef(new Set<string>());
  const isWorkflowProposal = proposal?.proposal_type === "resume_generation_request" || proposal?.proposal_type === "interview_preparation_request";
  const isJobProposal = proposal?.proposal_type === "job_radar_action";

  const copy = useMemo(() => lang === "zh" ? {
    title: "不平", empty: "告诉我你想分析或修改什么。选中右侧简历文字后，可以直接要求润色、缩短或校对。",
    placeholder: "输入你的要求…", apply: "应用到简历", runWorkflow: "开始生成", confirmAction: "确认操作", undo: "撤销修改", dismiss: "暂不采用",
    original: "原文", suggestion: "建议", loading: "正在处理", context: "上下文",
    addContext: "添加上下文", uploadDocument: "上传文档", uploading: "正在解析文档…",
    noContext: "未添加上下文", noAvailableContext: "当前没有其他可添加的上下文",
  } : {
    title: "Buping", empty: "Ask for analysis or edits. Select resume text on the right to rewrite it.",
    placeholder: "Describe what you need…", apply: "Apply to resume", runWorkflow: "Start generation", confirmAction: "Confirm action", undo: "Undo change", dismiss: "Dismiss",
    original: "Original", suggestion: "Suggestion", loading: "Working", context: "Context",
    addContext: "Add context", uploadDocument: "Upload document", uploading: "Parsing document…",
    noContext: "No context attached", noAvailableContext: "No other context is available",
  }, [lang]);

  const attachmentOptions = useMemo<WorkspaceContextDescriptor[]>(() => attachments.map((attachment) => ({
    id: `attachment:${attachment.id}`,
    label: attachment.filename,
    description: lang === "zh"
      ? `${attachment.character_count.toLocaleString()} 个字符`
      : `${attachment.character_count.toLocaleString()} characters`,
    snapshotKeys: [],
  })), [attachments, lang]);
  const contextOptions = useMemo(
    () => [...workspaceContextOptions, ...attachmentOptions],
    [attachmentOptions, workspaceContextOptions],
  );

  const refreshContexts = useCallback(async () => {
    const bridge = getWorkspaceBridge();
    if (!bridge || bridge.page !== page) {
      setWorkspaceContextOptions([]);
      return;
    }
    const snapshot = await bridge.getContextSnapshot();
    const options = bridge.describeContexts?.(snapshot) || [];
    setWorkspaceContextOptions(options);
    const available = new Set(options.map((item) => item.id));
    setAttachedContextIds((current) => {
      const next = current.filter((id) => id.startsWith("attachment:") || available.has(id));
      for (const option of options) {
        if (option.defaultAttached && !explicitlyDetachedRef.current.has(option.id) && !next.includes(option.id)) {
          next.push(option.id);
        }
      }
      return next;
    });
  }, [page]);

  useEffect(() => {
    let cancelled = false;
    setSessionId("");
    setMessages([]);
    setProposal(null);
    setError("");
    setLiveEvents([]);
    setStreamingMessage(null);
    setStreamedContent("");
    setWorkspaceContextOptions([]);
    setAttachments([]);
    setAttachedContextIds([]);
    setContextMenuOpen(false);
    explicitlyDetachedRef.current.clear();
    shouldFollowOutputRef.current = true;
    const storageKey = `buping_assistant_workspace_${page}`;
    let workspaceObjectId = window.sessionStorage.getItem(storageKey);
    if (!workspaceObjectId) {
      workspaceObjectId = `${page}-${crypto.randomUUID()}`;
      window.sessionStorage.setItem(storageKey, workspaceObjectId);
    }
    void createAssistantSession(page, workspaceObjectId).then((result) => {
      if (cancelled) return;
      setSessionId(result.session.id);
      setMessages(result.messages);
      setProposal(result.proposals[result.proposals.length - 1] || null);
      setAttachments(result.attachments || []);
      const active = result.active_runs?.[0];
      if (active) { setActiveRunId(active.id); setPending(true); setProgressStage("submitted"); }
    }).catch((cause) => {
      if (!cancelled) setError(cause?.response?.data?.detail || cause?.message || String(cause));
    });
    return () => { cancelled = true; };
  }, [page]);

  useEffect(() => {
    // A locally-started SSE stream is authoritative for both progress and the
    // final message. Polling the same run at this point can fetch the persisted
    // answer before result_end arrives and render it alongside the stream.
    // Poll only restored/interrupted runs that no longer have a live stream.
    if (!activeRunId || !sessionId || liveStreamActive) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const run = await getAssistantRun(activeRunId);
        if (cancelled || ["running", "cancel_requested"].includes(run.status)) return;
        const session = await getAssistantSession(sessionId);
        if (cancelled) return;
        setMessages(session.messages);
        setProposal(session.proposals[session.proposals.length - 1] || null);
        setPending(false);
        setActiveRunId("");
      } catch { /* the live SSE path remains authoritative */ }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1200);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeRunId, sessionId, liveStreamActive]);

  useEffect(() => {
    const refresh = () => { void refreshContexts(); };
    window.addEventListener("buping:workspace-context-changed", refresh);
    refresh();
    return () => window.removeEventListener("buping:workspace-context-changed", refresh);
  }, [refreshContexts]);

  useEffect(() => {
    const container = messageListRef.current;
    if (!container || !shouldFollowOutputRef.current) return;
    container.scrollTop = container.scrollHeight;
  }, [messages, liveEvents, streamedContent, proposal, error]);

  const handleMessageScroll = () => {
    const container = messageListRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldFollowOutputRef.current = distanceFromBottom <= 32;
  };

  const handleAttachmentUpload = async (file?: File) => {
    if (!file || !sessionId || uploadingAttachment) return;
    setUploadingAttachment(true);
    setError("");
    try {
      const attachment = await uploadAssistantAttachment(sessionId, file);
      const ref = `attachment:${attachment.id}`;
      setAttachments((current) => [...current.filter((item) => item.id !== attachment.id), attachment]);
      setAttachedContextIds((current) => current.includes(ref) ? current : [...current, ref]);
      explicitlyDetachedRef.current.delete(ref);
      setContextMenuOpen(false);
    } catch (cause: any) {
      setError(cause?.response?.data?.detail || cause?.message || String(cause));
    } finally {
      setUploadingAttachment(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const message = input.trim();
    if (!message || !sessionId || pending) return;
    setInput("");
    setPending(true);
    setProgressStage("context");
    setLiveEvents([]);
    setStreamingMessage(null);
    setStreamedContent("");
    setLiveStreamActive(true);
    setError("");
    const optimisticContexts = contextOptions.filter((item) => attachedContextIds.includes(item.id));
    const optimisticContextLabels = Object.fromEntries(
      optimisticContexts.map((item) => [item.id, item.label]),
    );
    const optimistic: AssistantMessage = {
      id: `local-${Date.now()}`, session_id: sessionId, role: "user", content: message,
      status: "completed", run_id: null,
      metadata: { context_refs: optimisticContexts.map((item) => item.id), context_labels: optimisticContextLabels },
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    try {
      const bridge = getWorkspaceBridge();
      const fullSnapshot = bridge && bridge.page === page ? await bridge.getContextSnapshot() : {};
      const activeContexts = contextOptions.filter((item) => attachedContextIds.includes(item.id));
      const snapshot = selectWorkspaceContext(fullSnapshot, activeContexts);
      const contextRefs = activeContexts.map((item) => item.id);
      const contextLabels = Object.fromEntries(activeContexts.map((item) => [item.id, item.label]));
      const settings = await getSettings();
      setProgressStage("submitted");
      await streamAssistantMessage(sessionId, {
        message, page, workspace_snapshot: snapshot, context_refs: contextRefs, context_labels: contextLabels,
        selected_objects: activeContexts.flatMap((item) => item.selectedObjects || []),
        api_key: settings.llm_api_key || "", provider: settings.llm_model_type || "",
        model: settings.llm_model || "", base_url: settings.llm_base_url || "",
      }, (streamEvent) => {
        if (streamEvent.type === "progress") {
          const next = streamEvent.data as RuntimeEvent;
          if (next.run_id) setActiveRunId(String(next.run_id));
          setLiveEvents((current) => {
            let pendingIndex = -1;
            for (let index = current.length - 1; index >= 0; index -= 1) {
              if (current[index].stage === next.stage && current[index].status === "running") {
                pendingIndex = index;
                break;
              }
            }
            if (pendingIndex < 0) return [...current, next];
            const updated = [...current];
            updated[pendingIndex] = next;
            return updated;
          });
        } else if (streamEvent.type === "result_start") {
          setStreamingMessage(streamEvent.data.assistant_message);
          setStreamedContent("");
        } else if (streamEvent.type === "content_delta") {
          setStreamedContent((current) => current + streamEvent.data.delta);
        } else if (streamEvent.type === "result_end") {
          const result = streamEvent.data;
          setMessages((current) => [
            ...current.filter((item) => item.id !== optimistic.id),
            result.user_message,
            result.assistant_message,
          ]);
          setProposal(result.proposal);
          setStreamingMessage(null);
          setStreamedContent("");
          setActiveRunId("");
        } else if (streamEvent.type === "error") {
          throw new Error(streamEvent.data.detail || "Assistant stream failed");
        }
      });
    } catch (cause: any) {
      setMessages((current) => current.filter((item) => item.id !== optimistic.id));
      setError(cause?.response?.data?.detail || cause?.message || String(cause));
    } finally {
      setLiveStreamActive(false);
      setPending(false);
    }
  };

  const handleCancel = async () => {
    if (!activeRunId) return;
    try {
      await cancelAssistantRun(activeRunId);
      setLiveEvents((current) => [...current, { stage: "cancel_requested", detail: lang === "zh" ? "正在安全停止运行" : "Stopping safely", status: "running" }]);
    } catch (cause: any) {
      setError(cause?.response?.data?.detail || cause?.message || String(cause));
    }
  };

  const handleApply = async () => {
    if (!proposal) return;
    const bridge = getWorkspaceBridge();
    if (!bridge?.applyProposal) {
      setError(lang === "zh" ? "当前工作区无法应用此建议。" : "This workspace cannot apply the proposal.");
      return;
    }
    try {
      const confirmation = await confirmAssistantProposal(proposal.id);
      await bridge.applyProposal(proposal);
      const applied = await applyAssistantProposal(proposal.id, confirmation.confirmation_token);
      setProposal(applied.proposal_type === "resume_text_rewrite" ? applied : null);
    } catch (cause: any) {
      setError(cause?.message || String(cause));
    }
  };

  const handleDismiss = async () => {
    if (!proposal) return;
    await dismissAssistantProposal(proposal.id).catch(() => undefined);
    setProposal(null);
  };

  const handleUndo = async () => {
    if (!proposal || proposal.status !== "applied") return;
    const bridge = getWorkspaceBridge();
    if (!bridge?.undoProposal) return;
    try {
      await bridge.undoProposal(proposal);
      await undoAssistantProposal(proposal.id);
      setProposal(null);
    } catch (cause: any) {
      setError(cause?.response?.data?.detail || cause?.message || String(cause));
    }
  };

  return (
    <aside className="flex h-[calc(100dvh-6rem)] min-h-[420px] flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm lg:h-[calc(100dvh-1.5rem)] lg:min-h-0 dark:border-gray-700 dark:bg-gray-800">
      <header className="flex items-center gap-2 border-b border-gray-200 px-4 py-3 dark:border-gray-700">
        <span className="rounded-lg bg-brand-50 p-2 text-brand-600 dark:bg-brand-900/30"><Bot className="h-5 w-5" /></span>
        <div><h2 className="text-sm font-semibold text-gray-900 dark:text-white">{copy.title}</h2><p className="text-[11px] text-gray-500">Supervisor · 有界受控执行</p></div>
      </header>
      <div
        ref={messageListRef}
        onScroll={handleMessageScroll}
        className="flex-1 space-y-3 overflow-y-auto px-3 py-4"
      >
        {!messages.length && !pending && (
          <div className="rounded-xl bg-gray-50 p-4 text-sm leading-6 text-gray-500 dark:bg-gray-900/50 dark:text-gray-400">
            <Sparkles className="mb-2 h-5 w-5 text-brand-500" />{copy.empty}
          </div>
        )}
        {messages.map((message) => (
          <div key={message.id}>
            {message.role === "user" ? (
              <div className="flex flex-col items-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2 text-sm leading-6 text-white">
                  {message.content}
                </div>
                <ContextBadges
                  refs={Array.isArray(message.metadata?.context_refs) ? message.metadata.context_refs : []}
                  labels={message.metadata?.context_labels || {}}
                  options={contextOptions}
                  lang={lang}
                />
              </div>
            ) : (
              <AssistantMarkdown content={message.content} />
            )}
            {message.role === "assistant" && message.run_id && (
              <RunProgress
                lang={lang}
                metadata={message.metadata}
                failed={message.status === "failed"}
              />
            )}
          </div>
        ))}
        {pending && <RunProgress lang={lang} running stage={progressStage} events={liveEvents} onCancel={activeRunId ? handleCancel : undefined} />}
        {streamingMessage && !messages.some((message) => message.id === streamingMessage.id) && (
          <AssistantMarkdown content={streamedContent} streaming />
        )}
        {proposal && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs dark:border-amber-800 dark:bg-amber-950/30">
            {isJobProposal ? (
              <p className="text-gray-700 dark:text-gray-200">{lang === "zh" ? `${proposal.payload.job?.company || ""} · ${proposal.payload.job?.role || "岗位"}：${proposal.payload.action === "favorite_job" ? "收藏" : proposal.payload.action === "not_interested_job" ? "标记为不感兴趣" : "打开投递信息确认"}` : `${proposal.payload.job?.company || ""} · ${proposal.payload.job?.role || "Job"}: ${proposal.payload.action}`}</p>
            ) : isWorkflowProposal ? (
              <p className="text-gray-700 dark:text-gray-200">{proposal.proposal_type === "resume_generation_request"
                ? (lang === "zh" ? `将使用右侧当前设置生成：${proposal.payload.target_pages || 1} 页 · ${proposal.payload.generation_mode === "partial" ? "局部修改" : "全新生成"}` : `Generate with current settings: ${proposal.payload.target_pages || 1} page(s) · ${proposal.payload.generation_mode || "new"}`)
                : (lang === "zh" ? `将生成面试准备报告：${proposal.payload.interview_type || "综合面试"} · ${proposal.payload.question_count || 10} 题` : `Generate interview preparation: ${proposal.payload.interview_type || "general"} · ${proposal.payload.question_count || 10} questions`)}</p>
            ) : <><p className="mb-1 font-semibold text-amber-900 dark:text-amber-200">{copy.original}</p><p className="max-h-24 overflow-auto text-gray-600 line-through dark:text-gray-400">{proposal.payload.original_text}</p><p className="mb-1 mt-3 font-semibold text-amber-900 dark:text-amber-200">{copy.suggestion}</p><p className="max-h-40 overflow-auto whitespace-pre-wrap text-gray-800 dark:text-gray-100">{proposal.payload.replacement_text}</p></>}
            <div className="mt-3 flex gap-2">
              {proposal.status === "applied" ? (
                <button onClick={handleUndo} className="rounded-lg border border-brand-300 px-3 py-2 font-medium text-brand-700 dark:border-brand-700 dark:text-brand-300">{copy.undo}</button>
              ) : <>
                <button onClick={handleApply} className="flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-2 font-medium text-white"><Check className="h-3.5 w-3.5" />{isWorkflowProposal ? copy.runWorkflow : isJobProposal ? copy.confirmAction : copy.apply}</button>
                <button onClick={handleDismiss} className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-gray-600 dark:border-gray-600 dark:text-gray-300"><X className="h-3.5 w-3.5" />{copy.dismiss}</button>
              </>}
            </div>
          </div>
        )}
        {error && <p className="rounded-lg bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">{error}</p>}
      </div>
      <form onSubmit={submit} className="border-t border-gray-200 p-3 dark:border-gray-700">
        <div className="relative mb-2">
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="mr-0.5 flex items-center gap-1 text-gray-500 dark:text-gray-400">
              <Paperclip className="h-3.5 w-3.5" />{copy.context}
            </span>
            {contextOptions.filter((item) => attachedContextIds.includes(item.id)).map((item) => (
              <span key={item.id} title={item.description} className="flex max-w-full items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-gray-600 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300">
                <span className="truncate">{item.label}</span>
                <button
                  type="button"
                  aria-label={`${lang === "zh" ? "移除" : "Remove"} ${item.label}`}
                  onClick={() => {
                    explicitlyDetachedRef.current.add(item.id);
                    setAttachedContextIds((current) => current.filter((id) => id !== item.id));
                  }}
                  className="rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-100"
                ><X className="h-3 w-3" /></button>
              </span>
            ))}
            {!attachedContextIds.length && <span className="text-gray-400">{copy.noContext}</span>}
            <button
              type="button"
              onClick={() => { void refreshContexts(); setContextMenuOpen((open) => !open); }}
              className="flex items-center gap-1 rounded-md px-1.5 py-1 text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:hover:bg-gray-700 dark:hover:text-gray-100"
            ><Plus className="h-3.5 w-3.5" />{copy.addContext}</button>
          </div>
          {contextMenuOpen && (
            <div className="absolute bottom-full left-0 z-20 mb-2 flex max-h-[min(55vh,28rem)] w-full max-w-sm flex-col overflow-hidden rounded-lg border border-gray-200 bg-white p-1.5 shadow-lg dark:border-gray-600 dark:bg-gray-800">
              <button
                type="button"
                disabled={uploadingAttachment || !sessionId}
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                {uploadingAttachment
                  ? <LoaderCircle className="h-4 w-4 animate-spin" />
                  : <FileUp className="h-4 w-4" />}
                {uploadingAttachment ? copy.uploading : copy.uploadDocument}
                <span className="ml-auto text-[10px] font-normal text-gray-400">PDF · DOCX · TXT · MD</span>
              </button>
              <div className="my-1 border-t border-gray-100 dark:border-gray-700" />
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-0.5">
                {contextOptions.length ? contextOptions.map((item) => {
                  const attached = attachedContextIds.includes(item.id);
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        if (attached) {
                          explicitlyDetachedRef.current.add(item.id);
                          setAttachedContextIds((current) => current.filter((id) => id !== item.id));
                        } else {
                          explicitlyDetachedRef.current.delete(item.id);
                          setAttachedContextIds((current) => [...current, item.id]);
                        }
                      }}
                      className="flex w-full items-start gap-2 rounded-md px-2 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${attached ? "border-brand-600 bg-brand-600 text-white" : "border-gray-300 dark:border-gray-500"}`}>
                        {attached && <Check className="h-3 w-3" />}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-medium text-gray-800 dark:text-gray-100">{item.label}</span>
                        {item.description && <span className="block truncate text-[11px] text-gray-400">{item.description}</span>}
                      </span>
                    </button>
                  );
                }) : <p className="px-2 py-3 text-xs text-gray-400">{copy.noAvailableContext}</p>}
              </div>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.markdown,.html,.htm,.tex,.yaml,.yml"
            className="hidden"
            onChange={(event) => { void handleAttachmentUpload(event.target.files?.[0]); }}
          />
        </div>
        <div className="flex items-end gap-2 rounded-xl border border-gray-300 bg-white p-2 focus-within:border-brand-500 dark:border-gray-600 dark:bg-gray-900">
          <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder={copy.placeholder}
            rows={2} className="max-h-32 min-h-[44px] flex-1 resize-none bg-transparent px-1 text-sm outline-none dark:text-white"
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
          <button type="submit" disabled={!input.trim() || pending || !sessionId} className="rounded-lg bg-brand-600 p-2 text-white disabled:opacity-40"><Send className="h-4 w-4" /></button>
        </div>
      </form>
    </aside>
  );
}

function selectWorkspaceContext(
  snapshot: WorkspaceSnapshot,
  contexts: WorkspaceContextDescriptor[],
): WorkspaceSnapshot {
  const selected: Record<string, unknown> = {};
  for (const context of contexts) {
    for (const key of context.snapshotKeys) {
      if (snapshot[key] !== undefined) selected[key] = snapshot[key];
    }
  }
  return selected as WorkspaceSnapshot;
}

function ContextBadges({ refs, labels, options, lang }: {
  refs: string[];
  labels: Record<string, string>;
  options: WorkspaceContextDescriptor[];
  lang: Lang;
}) {
  if (!refs.length) return null;
  const fallback: Record<string, string> = lang === "zh" ? {
    "resume.current": "当前简历",
    "resume.selection": "选中的简历文本",
    "resume.job_description": "职位描述",
    "interview.job_description": "职位描述",
    "interview.report": "面试准备报告",
    "coding.task": "当前编程题",
    "coding.code": "当前代码",
    "radar.preferences": "求职偏好",
    "radar.results": "当前岗位结果",
  } : {
    "resume.current": "Current resume",
    "resume.selection": "Selected resume text",
    "resume.job_description": "Job description",
    "interview.job_description": "Job description",
    "interview.report": "Interview prep report",
    "coding.task": "Current coding task",
    "coding.code": "Current code",
    "radar.preferences": "Job preferences",
    "radar.results": "Current job results",
  };
  return (
    <div className="mt-1 flex max-w-[85%] flex-wrap justify-end gap-1 text-[10px] text-gray-400">
      <Paperclip className="mt-0.5 h-3 w-3" />
      {refs.map((ref) => (
        <span key={ref}>{labels[ref] || options.find((item) => item.id === ref)?.label || fallback[ref] || ref}</span>
      ))}
    </div>
  );
}

function AssistantMarkdown({ content, streaming = false }: { content: string; streaming?: boolean }) {
  return (
    <div className="w-full px-1 py-1 text-sm leading-7 text-gray-800 dark:text-gray-100">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="mb-3 mt-5 text-xl font-bold first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-5 text-base font-semibold first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1.5 mt-4 font-semibold first:mt-0">{children}</h3>,
          p: ({ children }) => <p className="my-2 whitespace-pre-wrap">{children}</p>,
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-gray-950 dark:text-white">{children}</strong>,
          blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-gray-300 pl-3 text-gray-600 dark:border-gray-600 dark:text-gray-300">{children}</blockquote>,
          code: ({ children }) => <code className="break-words rounded bg-gray-100 px-1 py-0.5 text-[0.9em] dark:bg-gray-700">{children}</code>,
          table: ({ children }) => <table className="my-3 w-full table-fixed border-collapse text-left text-xs">{children}</table>,
          th: ({ children }) => <th className="break-words border border-gray-200 bg-gray-50 px-2 py-1.5 font-semibold dark:border-gray-700 dark:bg-gray-800">{children}</th>,
          td: ({ children }) => <td className="break-words border border-gray-200 px-2 py-1.5 align-top dark:border-gray-700">{children}</td>,
        }}
      >
        {content || (streaming ? " " : "")}
      </ReactMarkdown>
      {streaming && <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-brand-500 align-middle" />}
    </div>
  );
}
