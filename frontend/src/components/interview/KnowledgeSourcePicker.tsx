import { useEffect, useRef, useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, Download, Loader2, RefreshCw, Trash2, Upload } from "lucide-react";
import {
  deleteInterviewKnowledgeSource, getInterviewKnowledgeSources,
  getInterviewKnowledgeCatalog, installInterviewKnowledgeCatalogSource,
  rebuildInterviewKnowledgeCatalogSource, uninstallInterviewKnowledgeCatalogSource,
  type InterviewKnowledgeSource, type PublicInterviewKnowledgeCatalogItem,
  uploadInterviewKnowledge,
} from "../../api/client";

export default function KnowledgeSourcePicker({
  selected, onChange, disabled = false,
}: { selected: string[]; onChange: (ids: string[]) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [sources, setSources] = useState<InterviewKnowledgeSource[]>([]);
  const [catalog, setCatalog] = useState<PublicInterviewKnowledgeCatalogItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [busySourceId, setBusySourceId] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    const [sourceResult, catalogResult] = await Promise.all([
      getInterviewKnowledgeSources(), getInterviewKnowledgeCatalog(),
    ]);
    setSources(sourceResult.items);
    setCatalog(catalogResult.items);
    onChange(selected.filter((id) => sourceResult.items.some((source) => source.id === id && source.sync_status === "ready")));
  };

  useEffect(() => { void refresh().catch(() => setError("知识库加载失败")); }, []);

  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const result = await uploadInterviewKnowledge(file);
      await refresh();
      onChange(Array.from(new Set([...selected, result.source.id])));
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "导入失败");
    } finally { setBusy(false); if (inputRef.current) inputRef.current.value = ""; }
  };

  const toggle = (source: InterviewKnowledgeSource) => {
    if (source.sync_status !== "ready") return;
    onChange(selected.includes(source.id) ? selected.filter((id) => id !== source.id) : [...selected, source.id]);
  };

  const runCatalogAction = async (
    item: PublicInterviewKnowledgeCatalogItem, action: "install" | "rebuild" | "remove",
  ) => {
    if (action === "install" && !window.confirm(
      `${item.license_notice}\n\n点击“确定”表示同意按 ${item.license} 许可下载并在本地建立索引。`,
    )) return;
    if (action === "remove" && !window.confirm(`删除“${item.name}”的本地源文件和索引？`)) return;
    setBusy(true); setBusySourceId(item.id); setError("");
    try {
      if (action === "install") {
        await installInterviewKnowledgeCatalogSource(item.id);
      } else if (action === "rebuild") {
        await rebuildInterviewKnowledgeCatalogSource(item.id);
      } else {
        await uninstallInterviewKnowledgeCatalogSource(item.id);
        onChange(selected.filter((id) => id !== item.id));
      }
      await refresh();
      if (action === "install") onChange(Array.from(new Set([...selected, item.id])));
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "知识库操作失败");
    } finally { setBusy(false); setBusySourceId(""); }
  };

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
      <button type="button" onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-gray-700 dark:text-gray-200">
        <span className="flex items-center gap-2"><BookOpen className="h-3.5 w-3.5 text-brand-500" />面试知识库 · {selected.length || "自动"}</span>
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {open && <div className="max-h-56 space-y-2 overflow-y-auto border-t border-gray-200 p-3 dark:border-gray-700">
        <p className="text-[11px] leading-4 text-gray-500">未勾选时自动使用全部可用知识库；支持 Markdown、JSON、PDF、DOCX、ZIP。</p>
        {catalog.length > 0 && <div className="space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">可安装公共知识库</p>
          {catalog.map((item) => <div key={item.id} className="rounded-md border border-gray-200 p-2 dark:border-gray-700">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <span className="block truncate text-xs font-medium text-gray-700 dark:text-gray-200">{item.name}</span>
                <span className="mt-0.5 block text-[10px] leading-4 text-gray-400">{item.description}</span>
                <span className="block text-[10px] text-gray-400">
                  {item.license} · {item.revision.slice(0, 7)}
                  {item.installed ? ` · 已安装 ${item.stats.units} 条` : " · 尚未安装"}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {!item.installed ? <button type="button" disabled={busy || disabled}
                  onClick={() => void runCatalogAction(item, "install")}
                  className="flex items-center gap-1 rounded bg-brand-600 px-2 py-1 text-[10px] text-white disabled:opacity-50">
                  {busySourceId === item.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}安装
                </button> : <>
                  <button type="button" title={item.update_available ? "更新并重建" : "重新构建索引"}
                    disabled={busy || disabled} onClick={() => void runCatalogAction(item, item.update_available ? "install" : "rebuild")}
                    className="rounded p-1 text-gray-400 hover:text-brand-600 disabled:opacity-50">
                    <RefreshCw className={`h-3.5 w-3.5 ${busySourceId === item.id ? "animate-spin" : ""}`} />
                  </button>
                  <button type="button" title="删除本地副本" disabled={busy || disabled}
                    onClick={() => void runCatalogAction(item, "remove")}
                    className="rounded p-1 text-gray-400 hover:text-red-500 disabled:opacity-50">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </>}
              </div>
            </div>
            {!item.installed && <p className="mt-1 text-[9px] leading-3 text-amber-600 dark:text-amber-400">{item.license_notice}</p>}
          </div>)}
        </div>}
        <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">当前可用来源</p>
        {sources.map((source) => <div key={source.id} className="flex items-center gap-2 text-xs">
          <input type="checkbox" checked={selected.includes(source.id)} disabled={disabled || source.sync_status !== "ready"}
            onChange={() => toggle(source)} className="accent-brand-600" />
          <button type="button" onClick={() => toggle(source)} className="min-w-0 flex-1 text-left" disabled={disabled}>
            <span className="block truncate text-gray-700 dark:text-gray-200">{source.name}</span>
            <span className="text-[10px] text-gray-400">{source.stats.units} 条 · {source.scope === "public" ? "公共" : "私有"}</span>
          </button>
          {source.scope === "user" && <button type="button" title="删除" disabled={busy || disabled}
            onClick={async () => { setBusy(true); try { await deleteInterviewKnowledgeSource(source.id); onChange(selected.filter((id) => id !== source.id)); await refresh(); } finally { setBusy(false); } }}
            className="text-gray-400 hover:text-red-500"><Trash2 className="h-3.5 w-3.5" /></button>}
        </div>)}
        {!sources.length && <p className="text-xs text-gray-400">尚无可用知识库，可安装公共库或导入个人资料</p>}
        <input ref={inputRef} type="file" className="hidden" accept=".md,.markdown,.json,.pdf,.docx,.zip"
          onChange={(event) => void upload(event.target.files?.[0])} />
        <button type="button" disabled={busy || disabled} onClick={() => inputRef.current?.click()}
          className="flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-gray-300 px-2 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}导入个人资料
        </button>
        {error && <p className="text-[11px] text-red-500">{error}</p>}
      </div>}
    </div>
  );
}
