import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock3, Code2, History, Loader2, Play, Send, XCircle } from "lucide-react";
import type { Strings } from "../i18n";
import {
  getAICodingSessions, getAICodingTasks, startAICodingSession, submitAICodingSession,
  type AICodingReport, type AICodingTask, type AICodingTaskSummary,
} from "../api/client";
import { useWorkspaceBridgeRegistration, type WorkspaceSnapshot } from "../assistant/workspaceBridge";

type SessionRow = Awaited<ReturnType<typeof getAICodingSessions>>[number];

export default function AICodingPractice({ t }: { t: Strings }) {
  const english = t.nav.aiCoding === "AI Coding Practice";
  const [tasks, setTasks] = useState<AICodingTaskSummary[]>([]);
  const [history, setHistory] = useState<SessionRow[]>([]);
  const [task, setTask] = useState<AICodingTask | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [code, setCode] = useState("");
  const [approach, setApproach] = useState("");
  const [testStrategy, setTestStrategy] = useState("");
  const [aiReflection, setAiReflection] = useState("");
  const [startedAt, setStartedAt] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [report, setReport] = useState<AICodingReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const assistantBridge = useMemo(() => ({
    page: "ai-coding",
    workspaceObjectId: sessionId || "default",
    selectedObjects: [],
    getContextSnapshot: (): WorkspaceSnapshot => ({
      language: english ? "en" : "zh",
      coding_task: task ? {
        id: task.id, title: task.title, description: task.description,
        requirements: task.requirements, examples: task.examples,
      } : undefined,
      coding_code: code,
    }),
    describeContexts: (snapshot: WorkspaceSnapshot) => [
      ...(snapshot.coding_task ? [{
        id: "coding.task", label: english ? "Current coding task" : "当前编程题",
        description: String(snapshot.coding_task.title || ""),
        snapshotKeys: ["coding_task", "language"] as Array<keyof WorkspaceSnapshot>, defaultAttached: true,
      }] : []),
      ...(snapshot.coding_code?.trim() ? [{
        id: "coding.code", label: english ? "Current code" : "当前代码",
        description: `${snapshot.coding_code.split("\n").length} ${english ? "lines" : "行"}`,
        snapshotKeys: ["coding_code", "language"] as Array<keyof WorkspaceSnapshot>, defaultAttached: true,
      }] : []),
    ],
  }), [code, english, sessionId, task]);
  useWorkspaceBridgeRegistration(assistantBridge);

  const reload = async () => {
    const [nextTasks, nextHistory] = await Promise.all([getAICodingTasks(), getAICodingSessions()]);
    setTasks(nextTasks); setHistory(nextHistory);
  };
  useEffect(() => { reload().catch((err) => setError(err.message)); }, []);
  useEffect(() => {
    if (!startedAt || report) return;
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, report]);

  const clock = useMemo(() => `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`, [elapsed]);
  const begin = async (taskId: string) => {
    setLoading(true); setError(""); setReport(null);
    try {
      const result = await startAICodingSession(taskId);
      setTask(result.task); setSessionId(result.session.id); setCode(result.task.starter_code);
      setApproach(""); setTestStrategy(""); setAiReflection(""); setElapsed(0); setStartedAt(Date.now());
      await reload();
    } catch (err: any) { setError(err.response?.data?.detail || err.message); }
    finally { setLoading(false); }
  };
  const submit = async () => {
    if (!sessionId || !code.trim()) return;
    setLoading(true); setError("");
    try {
      const result = await submitAICodingSession(sessionId, {
        code, approach, test_strategy: testStrategy, ai_reflection: aiReflection,
      });
      setReport(result.report); await reload();
    } catch (err: any) { setError(err.response?.data?.detail || err.message); }
    finally { setLoading(false); }
  };

  return <div className="page-enter mx-auto flex h-full max-w-6xl min-h-0 flex-col gap-3 overflow-hidden">
    <div className="flex-none">
      <h2 className="flex items-center gap-2 text-xl font-bold text-gray-900 dark:text-white"><Code2 className="text-brand-600" />{english ? "AI Coding Practice" : "AI Coding 训练场"}</h2>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{english ? "Practice the complete loop: understand, implement, verify, and reflect on AI collaboration." : "练习理解任务、实现代码、验证结果和复盘 AI 协作的完整闭环。"}</p>
    </div>
    {error && <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">{error}</div>}

    {!task && <section className="grid min-h-0 flex-1 gap-3 overflow-y-auto md:grid-cols-2">
      {tasks.map((item) => <article key={item.id} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold text-gray-900 dark:text-white">{item.title}</h3><p className="mt-2 text-sm text-gray-500">{item.summary}</p></div><span className="rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">{item.difficulty}</span></div>
        <div className="mt-4 flex items-center justify-between text-xs text-gray-500"><span>{item.language} · {item.duration_minutes} min</span><button disabled={loading} onClick={() => begin(item.id)} className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700 disabled:opacity-50"><Play className="h-4 w-4" />{english ? "Start" : "开始训练"}</button></div>
      </article>)}
    </section>}

    {task && <div className="grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[0.8fr_1.2fr]">
      <section className="space-y-4 overflow-y-auto rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-900 dark:text-white">{task.title}</h3><span className="flex items-center gap-1 font-mono text-sm text-gray-500"><Clock3 className="h-4 w-4" />{clock}</span></div>
        <p className="text-sm leading-6 text-gray-600 dark:text-gray-300">{task.description}</p>
        <div><h4 className="mb-2 text-sm font-semibold text-gray-800 dark:text-gray-200">{english ? "Requirements" : "要求"}</h4><ul className="list-disc space-y-1 pl-5 text-sm text-gray-600 dark:text-gray-300">{task.requirements.map((item) => <li key={item}>{item}</li>)}</ul></div>
        {task.examples.map((example, index) => <div key={index} className="rounded-lg bg-gray-50 p-3 font-mono text-xs dark:bg-gray-900"><div>Input: {example.input}</div><div className="mt-1">Output: {example.output}</div></div>)}
        <button onClick={() => { setTask(null); setReport(null); }} className="text-xs text-gray-500 hover:text-brand-600">← {english ? "Back to tasks" : "返回题目列表"}</button>
      </section>
      <section className="min-h-0 space-y-3 overflow-y-auto pr-1">
        <div className="rounded-xl border border-gray-200 bg-gray-950 p-4 shadow-sm"><div className="mb-3 text-xs font-medium text-gray-400">solution.py</div><textarea spellCheck={false} value={code} onChange={(e) => setCode(e.target.value)} rows={14} className="w-full resize-y bg-transparent font-mono text-sm leading-6 text-emerald-300 outline-none" /></div>
        <div className="grid gap-3 md:grid-cols-3">
          <textarea value={approach} onChange={(e) => setApproach(e.target.value)} rows={4} placeholder={english ? "Explain your approach" : "说明你的解题思路与关键不变量"} className="rounded-xl border border-gray-300 p-3 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white" />
          <textarea value={testStrategy} onChange={(e) => setTestStrategy(e.target.value)} rows={4} placeholder={english ? "Describe your test strategy" : "你会覆盖哪些测试场景"} className="rounded-xl border border-gray-300 p-3 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white" />
          <textarea value={aiReflection} onChange={(e) => setAiReflection(e.target.value)} rows={4} placeholder={english ? "How did you use and verify AI?" : "你如何使用并验证 AI 的建议"} className="rounded-xl border border-gray-300 p-3 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white" />
        </div>
        {!report && <button disabled={loading} onClick={submit} className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 py-3 font-semibold text-white hover:bg-brand-700 disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{english ? "Submit and assess" : "提交并评分"}</button>}
        {report && <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-900 dark:text-white">{english ? "Assessment" : "训练评估"}</h3><strong className="text-3xl text-brand-600">{report.score}</strong></div>
          <p className="mt-2 text-sm text-gray-500">{english ? "Tests passed" : "测试通过"}: {report.passed_tests}/{report.total_tests}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">{Object.entries(report.dimensions).map(([key, value]) => <div key={key} className="rounded-lg bg-gray-50 p-3 dark:bg-gray-900"><div className="text-xs text-gray-500">{key}</div><div className="mt-1 font-semibold text-gray-900 dark:text-white">{value}</div></div>)}</div>
          <ul className="mt-4 space-y-2 text-sm text-gray-600 dark:text-gray-300">{report.feedback.map((item) => <li key={item} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 flex-none text-brand-500" />{item}</li>)}</ul>
          <div className="mt-4 space-y-2">{report.public_results.map((result, index) => <div key={index} className="flex items-center gap-2 text-xs">{result.passed ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <XCircle className="h-4 w-4 text-red-500" />} Public test {index + 1}{result.error ? `: ${result.error}` : ""}</div>)}</div>
        </div>}
      </section>
    </div>}

    <section className="max-h-36 flex-none overflow-y-auto rounded-xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-800"><h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white"><History className="h-4 w-4" />{english ? "Recent practice" : "最近训练"}</h3>{history.length === 0 ? <p className="text-xs text-gray-400">{english ? "No sessions yet." : "还没有训练记录。"}</p> : <div>{history.slice(0, 4).map((item) => <div key={item.id} className="flex items-center justify-between border-t border-gray-100 py-1.5 text-xs dark:border-gray-700"><span className="truncate text-gray-700 dark:text-gray-200">{item.task_title}</span><span className="ml-2 flex-none text-gray-500">{item.status === "completed" ? `${item.score}/100` : (english ? "In progress" : "进行中")}</span></div>)}</div>}</section>
  </div>;
}
