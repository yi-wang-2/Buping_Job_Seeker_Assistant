import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Brain, Clock3, Database, Gauge, RefreshCw, Server, Zap } from "lucide-react";
import { getAIMetrics, type AIMetrics } from "../api/client";
import type { Strings } from "../i18n";

const EMPTY: AIMetrics = {
  period_days: 30,
  summary: {
    calls: 0, successful_calls: 0, errors: 0, success_rate: 0, input_tokens: 0,
    output_tokens: 0, total_tokens: 0, retries: 0, avg_latency_ms: 0, p95_latency_ms: 0,
    cache_hits: 0, cache_entries: 0, cache_hit_rate: 0, memory_items: 0,
    context_original_tokens: 0, context_final_tokens: 0, context_saved_tokens: 0,
    context_compression_rate: 0, compressed_items: 0, dropped_items: 0,
  },
  by_skill: [], by_model: [], timeline: [], recent: [],
};

const number = new Intl.NumberFormat("zh-CN");

export default function AIMonitoring({ t }: { t: Strings }) {
  const english = t.nav.aiMonitoring === "AI Monitoring";
  const [days, setDays] = useState(30);
  const [metrics, setMetrics] = useState<AIMetrics>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setMetrics(await getAIMetrics(days));
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { void load(); }, [load]);
  const maxDailyTokens = useMemo(() => Math.max(1, ...metrics.timeline.map((item) => item.tokens)), [metrics.timeline]);
  const s = metrics.summary;
  const cards = [
    { label: english ? "Total tokens" : "总 Token", value: number.format(s.total_tokens), detail: `${number.format(s.input_tokens)} in / ${number.format(s.output_tokens)} out`, icon: Zap, color: "text-amber-500" },
    { label: english ? "Calls" : "调用次数", value: number.format(s.calls), detail: `${s.success_rate}% ${english ? "success" : "成功率"}`, icon: Activity, color: "text-blue-500" },
    { label: english ? "Average latency" : "平均延迟", value: `${s.avg_latency_ms} ms`, detail: `P95 ${s.p95_latency_ms} ms`, icon: Clock3, color: "text-violet-500" },
    { label: english ? "Cache hit rate" : "缓存命中率", value: `${s.cache_hit_rate}%`, detail: `${s.cache_hits} hits / ${s.cache_entries} entries`, icon: Database, color: "text-emerald-500" },
    { label: english ? "Context saved" : "上下文节省", value: number.format(s.context_saved_tokens), detail: `${s.context_compression_rate}% ${english ? "compressed" : "压缩率"}`, icon: Gauge, color: "text-cyan-500" },
    { label: english ? "Long-term memories" : "长期记忆", value: number.format(s.memory_items), detail: `${s.compressed_items} compressed / ${s.dropped_items} dropped`, icon: Brain, color: "text-pink-500" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-bold text-gray-900 dark:text-white"><Server className="h-6 w-6 text-brand-500" />{english ? "AI Monitoring" : "AI 监控"}</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{english ? "Tokens, latency, cache, context and memory metrics" : "监控 Token、延迟、缓存、上下文和长期记忆指标"}</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={(event) => setDays(Number(event.target.value))} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-white">
            <option value={1}>{english ? "Today" : "最近 1 天"}</option><option value={7}>{english ? "7 days" : "最近 7 天"}</option><option value={30}>{english ? "30 days" : "最近 30 天"}</option><option value={90}>{english ? "90 days" : "最近 90 天"}</option>
          </select>
          <button onClick={() => void load()} disabled={loading} className="rounded-lg border border-gray-300 p-2 text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700" title={english ? "Refresh" : "刷新"}><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">{error}</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(({ label, value, detail, icon: Icon, color }) => <div key={label} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800"><div className="flex items-center justify-between"><span className="text-sm text-gray-500 dark:text-gray-400">{label}</span><Icon className={`h-5 w-5 ${color}`} /></div><div className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{value}</div><div className="mt-1 text-xs text-gray-400">{detail}</div></div>)}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800"><h3 className="mb-4 font-semibold text-gray-900 dark:text-white">{english ? "Token trend" : "Token 趋势"}</h3>{metrics.timeline.length === 0 ? <p className="py-10 text-center text-sm text-gray-400">{english ? "No data" : "暂无数据"}</p> : <div className="overflow-x-auto"><div className="flex h-48 min-w-max items-end justify-start gap-3">{metrics.timeline.map((item) => <div key={item.date} className="group flex w-12 flex-none flex-col items-center justify-end"><div title={`${item.date}: ${item.tokens} tokens`} className="w-8 max-w-8 rounded-t bg-brand-500 transition hover:bg-brand-600" style={{ height: `${Math.max(4, item.tokens / maxDailyTokens * 160)}px` }} /><span className="mt-2 w-full truncate text-center text-[10px] text-gray-400">{item.date.slice(5)}</span></div>)}</div></div>}</section>
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800"><h3 className="mb-4 font-semibold text-gray-900 dark:text-white">{english ? "Usage by skill" : "按 Skill 统计"}</h3><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase text-gray-400"><tr><th className="pb-3">Skill</th><th className="pb-3 text-right">{english ? "Calls" : "调用"}</th><th className="pb-3 text-right">Token</th><th className="pb-3 text-right">{english ? "Avg latency" : "平均延迟"}</th></tr></thead><tbody>{metrics.by_skill.map((row) => <tr key={row.skill} className="border-t border-gray-100 dark:border-gray-700"><td className="py-3 font-medium text-gray-800 dark:text-gray-200">{row.skill}</td><td className="py-3 text-right text-gray-500">{row.calls}</td><td className="py-3 text-right text-gray-500">{number.format(row.tokens)}</td><td className="py-3 text-right text-gray-500">{row.avg_latency_ms} ms</td></tr>)}</tbody></table>{metrics.by_skill.length === 0 && <p className="py-10 text-center text-sm text-gray-400">{english ? "No data" : "暂无数据"}</p>}</div></section>
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800"><h3 className="mb-4 font-semibold text-gray-900 dark:text-white">{english ? "Recent calls" : "最近调用"}</h3><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase text-gray-400"><tr><th className="pb-3">{english ? "Time" : "时间"}</th><th className="pb-3">Skill</th><th className="pb-3">Model</th><th className="pb-3 text-right">Token</th><th className="pb-3 text-right">{english ? "Latency" : "延迟"}</th><th className="pb-3 text-right">{english ? "Status" : "状态"}</th></tr></thead><tbody>{metrics.recent.slice(0, 20).map((row, index) => <tr key={`${row.trace_id}-${index}`} className="border-t border-gray-100 dark:border-gray-700"><td className="py-3 text-gray-500">{new Date(row.timestamp).toLocaleString()}</td><td className="py-3 text-gray-700 dark:text-gray-200">{row.skill || "unknown"}</td><td className="py-3 text-gray-500">{row.model}</td><td className="py-3 text-right text-gray-500">{number.format(row.usage?.total_tokens || 0)}</td><td className="py-3 text-right text-gray-500">{row.latency_ms || 0} ms</td><td className={`py-3 text-right ${row.status === "success" ? "text-green-600" : "text-red-600"}`}>{row.status}</td></tr>)}</tbody></table></div></section>
    </div>
  );
}
