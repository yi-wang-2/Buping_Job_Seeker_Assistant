import { useEffect, useRef, useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, Loader2, Trash2, Upload } from "lucide-react";
import {
  deleteInterviewKnowledgeSource, getInterviewKnowledgeSources,
  type InterviewKnowledgeSource, setInterviewKnowledgeEnabled, uploadInterviewKnowledge,
} from "../../api/client";

export default function KnowledgeSourcePicker({
  selected, onChange, disabled = false,
}: { selected: string[]; onChange: (ids: string[]) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [sources, setSources] = useState<InterviewKnowledgeSource[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    const result = await getInterviewKnowledgeSources();
    setSources(result.items);
    onChange(selected.filter((id) => result.items.some((source) => source.id === id && source.sync_status === "ready")));
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

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
      <button type="button" onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-gray-700 dark:text-gray-200">
        <span className="flex items-center gap-2"><BookOpen className="h-3.5 w-3.5 text-brand-500" />面试知识库 · {selected.length || "自动"}</span>
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {open && <div className="max-h-56 space-y-2 overflow-y-auto border-t border-gray-200 p-3 dark:border-gray-700">
        <p className="text-[11px] leading-4 text-gray-500">未勾选时自动使用全部可用知识库；支持 Markdown、JSON、PDF、DOCX、ZIP。</p>
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
        {!sources.length && <p className="text-xs text-gray-400">尚未导入知识库</p>}
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
