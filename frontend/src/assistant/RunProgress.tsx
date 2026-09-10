import { ChevronRight, CircleCheck, CircleDashed, CircleX, Square } from "lucide-react";
import type { Lang } from "../i18n";

interface RunMetadata {
  mode?: string;
  dispatch_path?: string;
  reason_code?: string;
  capability?: string;
  proposal_id?: string;
  total_tokens?: number;
  error_code?: string;
  context_events?: string[];
  artifact_is_dirty?: boolean;
  grounding_retry?: boolean;
  grounding_status?: string;
  grounding_removed_count?: number;
  mutation_status?: string;
  runtime_events?: RuntimeEvent[];
  execution_steps?: Array<Record<string, unknown>>;
}

export interface RuntimeEvent {
  stage: string;
  detail: string;
  status: "running" | "completed" | "degraded" | "rejected" | "failed" | string;
  timestamp?: string;
  [key: string]: unknown;
}

interface Props {
  lang: Lang;
  running?: boolean;
  stage?: "context" | "submitted";
  metadata?: RunMetadata;
  failed?: boolean;
  events?: RuntimeEvent[];
  onCancel?: () => void;
}

const MODE_ZH: Record<string, string> = {
  chat: "直接回复",
  clarification: "请求澄清",
  direct_skill: "单一 Skill",
  fixed_workflow: "固定工作流",
  agent_loop: "Agent Loop",
};

const EVENT_COPY: Record<string, { zh: string; en: string }> = {
  page_state_read: { zh: "已读取当前页面状态", en: "Read current page state" },
  resume_artifact_identified: { zh: "已定位当前简历版本", en: "Identified the current resume version" },
  resume_body_resolved: { zh: "已解析整份简历正文", en: "Resolved the full resume body" },
  selection_read: { zh: "已读取当前选中文本", en: "Read the current selection" },
  review_grounding_retried: { zh: "首次结果未通过依据校验，已完成一次受控重试", en: "Retried once after grounding validation failed" },
  review_grounding_degraded: { zh: "两次结果均未通过依据校验，已隐藏未经核验的结论", en: "Withheld ungrounded findings after two attempts" },
  mutation_harness_rejected: { zh: "改写未通过硬事实检查，未生成可应用修改", en: "Rewrite failed hard-fact checks; no applicable change was created" },
};

export default function RunProgress({ lang, running = false, stage = "submitted", metadata = {}, failed = false, events = [], onCancel }: Props) {
  const zh = lang === "zh";
  const mode = zh ? (MODE_ZH[metadata.mode || ""] || metadata.mode || "受控执行") : (metadata.mode || "controlled run");
  const tokens = Number(metadata.total_tokens || 0);
  const runtimeEvents = settleEvents(events.length ? events : (metadata.runtime_events || []));
  const reasoningEvents = runtimeEvents.filter((event) => event.stage === "model_reasoning");
  const executionEvents = runtimeEvents.filter((event) => event.stage !== "model_reasoning");
  const latest = runtimeEvents[runtimeEvents.length - 1];
  const summary = running
    ? (latest?.detail || (zh ? "正在处理" : "Working"))
    : failed
      ? (zh ? "处理失败" : "Run failed")
      : (zh ? `已完成 · ${mode}${tokens ? ` · ${tokens} tokens` : ""}` : `Completed · ${mode}${tokens ? ` · ${tokens} tokens` : ""}`);
  const Icon = running ? CircleDashed : failed ? CircleX : CircleCheck;

  return (
    <details open={running || undefined} className="group mt-1.5 text-[11px] text-gray-400 dark:text-gray-500">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded px-1 py-0.5 transition-colors hover:bg-gray-100 hover:text-gray-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-brand-500 dark:hover:bg-gray-700/60 dark:hover:text-gray-300 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
        <Icon className={`h-3 w-3 ${running ? "animate-spin" : ""}`} />
        <span>{summary}</span>
        {running && onCancel && <button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); onCancel(); }} className="ml-2 flex items-center gap-1 rounded border border-gray-200 px-1.5 py-0.5 hover:border-red-300 hover:text-red-500 dark:border-gray-700"><Square className="h-2.5 w-2.5" />{zh ? "停止" : "Stop"}</button>}
      </summary>
      <div className="ml-4 mt-1.5 space-y-1 border-l border-gray-200 pl-3 leading-5 dark:border-gray-700">
        {runtimeEvents.length > 0 ? (
          <>
            <p className="mb-1 font-medium text-gray-500 dark:text-gray-400">
              {zh ? "执行步骤" : "Execution steps"}
              {!runtimeEvents.some((event) => event.stage === "plan") && <span className="ml-1 font-normal text-gray-400">
                {zh ? "（单步任务按需执行，多步任务会显示计划）" : "(plans appear for multi-step tasks)"}
              </span>}
            </p>
            {executionEvents.map((event, index) => {
              const active = event.status === "running" && index === executionEvents.length - 1 && running;
              const EventIcon = active ? CircleDashed : event.status === "failed" || event.status === "rejected" ? CircleX : CircleCheck;
              return (
                <p key={`${event.stage}-${event.timestamp || index}`} className="flex items-start gap-1.5">
                  <EventIcon className={`mt-1 h-3 w-3 shrink-0 ${active ? "animate-spin" : ""}`} />
                  <span>{event.detail}{event.stage === "plan" && Array.isArray(event.plan) && <ol className="mt-1 list-decimal pl-4">{event.plan.map((item, planIndex) => <li key={planIndex}>{String(item)}</li>)}</ol>}</span>
                </p>
              );
            })}
            {reasoningEvents.length > 0 && (
              <details className="group/reasoning mt-1.5 rounded-md bg-gray-50/80 px-2 py-1 dark:bg-gray-800/60">
                <summary className="flex cursor-pointer list-none items-center gap-1 [&::-webkit-details-marker]:hidden">
                  <ChevronRight className="h-3 w-3 transition-transform group-open/reasoning:rotate-90" />
                  <span>{zh ? "模型分析过程（默认折叠）" : "Model analysis process (collapsed)"}</span>
                </summary>
                <div className="mt-1 space-y-1 pl-4">
                  {reasoningEvents.map((event, index) => (
                    <p key={`${event.stage}-${event.timestamp || index}`}>{event.detail}</p>
                  ))}
                  <p>{zh
                    ? "为保护隐私与避免展示未经核验的猜测，原始逐字思维链不会传输或保存。"
                    : "Raw hidden reasoning is neither transmitted nor stored."}</p>
                </div>
              </details>
            )}
          </>
        ) : running ? (
          <p className="flex items-center gap-1">
            <CircleDashed className="h-3 w-3 animate-spin" />
            {stage === "context"
              ? (zh ? "正在读取当前页面状态" : "Reading current page state")
              : (zh ? "Controller 正在判断所需能力和上下文" : "Controller is selecting capability and context")}
          </p>
        ) : (
          <>
            {(metadata.context_events || []).map((event) => (
              <p key={event}>✓ {EVENT_COPY[event]?.[zh ? "zh" : "en"] || event}</p>
            ))}
            {metadata.dispatch_path && <p>✓ {zh ? "路由" : "Route"}: {metadata.dispatch_path}</p>}
            {metadata.mode && <p>✓ {zh ? "执行模式" : "Execution mode"}: {mode}</p>}
            {metadata.capability && <p>✓ {zh ? "调用能力" : "Capability"}: {metadata.capability}</p>}
            {metadata.artifact_is_dirty && <p>✓ {zh ? "本次分析包含右侧未保存修改" : "Included unsaved workspace edits"}</p>}
            {Number(metadata.grounding_removed_count || 0) > 0 && (
              <p>✓ {zh
                ? `已隐藏 ${metadata.grounding_removed_count} 条无法核验的评价`
                : `Withheld ${metadata.grounding_removed_count} unverified findings`}</p>
            )}
            {metadata.reason_code && <p>✓ Policy: {metadata.reason_code}</p>}
            {metadata.proposal_id && <p>✓ {zh ? "已生成待确认 Proposal，未自动应用" : "Created a pending proposal; not auto-applied"}</p>}
            {tokens > 0 && <p>✓ Token usage: {tokens}</p>}
            {failed && metadata.error_code && <p>× Error: {metadata.error_code}</p>}
          </>
        )}
      </div>
    </details>
  );
}

function settleEvents(events: RuntimeEvent[]): RuntimeEvent[] {
  const settled: RuntimeEvent[] = [];
  for (const event of events) {
    let pendingIndex = -1;
    for (let index = settled.length - 1; index >= 0; index -= 1) {
      if (settled[index].stage === event.stage && settled[index].status === "running") {
        pendingIndex = index;
        break;
      }
    }
    if (pendingIndex < 0) settled.push(event);
    else settled[pendingIndex] = event;
  }
  return settled;
}
