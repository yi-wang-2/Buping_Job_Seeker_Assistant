import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  Rocket,
  PlusCircle,
  Check,
  FolderOpen,
  Download,
  MapPin,
  Tag,
  ExternalLink,
  BookOpen,
  PenSquare,
  Trash2,
  X,
  BookMarked,
  Save,
  Image as ImageIcon,
  FileDown,
  Server,
  History,
  LoaderCircle,
  LogIn,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import type { Strings } from "../i18n";
import {
  getJobTrackerRecords,
  saveJobTrackerRecords,
  checkAllJobFollowups,
  checkJobFollowup,
  completeJobFollowupLogin,
  connectJobFollowup,
  getJobFollowupSchedule,
  saveJobFollowupSchedule,
  subscribeJobTrackerStatusChanges,
  type JobEntry,
} from "../api/client";

/* ─── Types ─────────────────────────────────────────────── */

/* ─── Constants ─────────────────────────────────────────── */

const STORAGE_KEY = "myJobTrackerV4";
const trackerStorage = import.meta.env.VITE_DEPLOYMENT_MODE === "public" ? window.sessionStorage : window.localStorage;

const STATUSES = [
  "简历筛选",
  "笔试",
  "技术面",
  "技术面挂",
  "主管面",
  "主管面挂",
  "HR面",
  "Offer",
  "泡池子",
  "简历挂",
];

const PRESET_ICONS: Record<string, string> = {
  腾讯: "/api/job-tracker/icon/腾讯QQ.svg",
  大疆: "/api/job-tracker/icon/DJI大疆.svg",
  华为: "/api/job-tracker/icon/华为.svg",
  字节: "/api/job-tracker/icon/字节跳动.svg",
  阿里: "/api/job-tracker/icon/阿里巴巴.svg",
  百度: "/api/job-tracker/icon/百度.svg",
  美团: "/api/job-tracker/icon/美团.svg",
  小米: "/api/job-tracker/icon/小米.svg",
  小红书: "/api/job-tracker/icon/小红书.svg",
  快手: "/api/job-tracker/icon/快手.svg",
  拼多多: "/api/job-tracker/icon/拼多多.svg",
  滴滴: "/api/job-tracker/icon/滴滴出行.svg",
  科大: "/api/job-tracker/icon/科大讯飞.svg",
  电信: "/api/job-tracker/icon/中国电信.svg",
  京东: "/api/job-tracker/icon/京东.svg",
  智谱: "/api/job-tracker/icon/智谱logo.svg",
  deepseek: "/api/job-tracker/icon/deepseek.svg",
  kimi: "/api/job-tracker/icon/kimi.svg",
  宇树: "/api/job-tracker/icon/宇树.png",
  B站: "/api/job-tracker/icon/B站.svg",
  tplink: "/api/job-tracker/icon/tplink.svg",
};

const AVATAR_COLORS = [
  "bg-red-500",
  "bg-blue-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-violet-500",
  "bg-pink-500",
  "bg-cyan-500",
];

const DEFAULT_ENTRIES: JobEntry[] = [
  {
    id: Date.now() + 1,
    company: "腾讯",
    role: "C++后台开发工程师",
    base: "深圳",
    remark: "暑期实习",
    link: "https://careers.tencent.com",
    status: "技术面",
    icon: "/api/job-tracker/icon/腾讯QQ.svg",
    notes:
      "一面复盘：\n1. 详细问了 Linux epoll 的触发模式（LT/ET）与底层红黑树结构。\n2. 基于 Qt 的客户端和 IM 网络编程底层逻辑。\n3. 手撕：滑动窗口最大值问题。",
  },
];

function createInitialForm() {
  const now = new Date();
  const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
  return {
    company: "",
    role: "",
    base: "",
    remark: "",
    applied_at: localNow,
    link: "",
    status: "简历筛选",
  };
}

/* ─── Helpers ───────────────────────────────────────────── */

function getAvatarColor(name: string): string {
  if (!name) return AVATAR_COLORS[0];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function getStatusClass(status: string): string {
  if (status === "Offer") return "bg-green-100 text-green-700 shadow-sm shadow-green-200/50";
  if (status.includes("挂")) return "bg-red-100 text-red-700 shadow-sm shadow-red-200/50";
  if (status.includes("面")) return "bg-blue-100 text-blue-700 shadow-sm shadow-indigo-200/50";
  if (status === "泡池子") return "bg-amber-100 text-amber-700 shadow-sm shadow-amber-200/50";
  return "bg-indigo-100 text-indigo-700 shadow-sm shadow-indigo-200/50";
}

function detectPresetIcon(company: string): string {
  for (const [key, iconPath] of Object.entries(PRESET_ICONS)) {
    if (company.includes(key)) return iconPath;
  }
  return "";
}

/** Migrate old icon paths from the previous /company-icons/ location. */
function migrateIconPaths(records: JobEntry[]): JobEntry[] {
  return records.map((r) => ({
    ...r,
    followup_enabled: r.status.includes("挂") ? false : r.followup_enabled,
    icon: r.icon ? r.icon.replace("/company-icons/", "/api/job-tracker/icon/") : "",
  }));
}

/* ─── Component ─────────────────────────────────────────── */

interface Props {
  t: Strings;
}

export default function JobTracker({ t }: Props) {
  const jt = t.jobTracker;

  /* ---- state ---- */
  const [entries, setEntries] = useState<JobEntry[]>([]);
  const [form, setForm] = useState(createInitialForm);
  const [formFeedback, setFormFeedback] = useState<{ type: "error" | "success"; message: string } | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentEntry, setCurrentEntry] = useState<JobEntry | null>(null);
  const [tempNotes, setTempNotes] = useState("");
  const [syncStatus, setSyncStatus] = useState<"loading" | "synced" | "unsaved" | "error">("loading");
  const [followupEntry, setFollowupEntry] = useState<JobEntry | null>(null);
  const [followupDraft, setFollowupDraft] = useState({ enabled: false, aiEnabled: true, platform: "generic", url: "" });
  const [followupBusy, setFollowupBusy] = useState(false);
  const [followupMessage, setFollowupMessage] = useState("");
  const [followupInterval, setFollowupInterval] = useState(8);
  const [scheduleStatus, setScheduleStatus] = useState("");
  const [followupRuntime, setFollowupRuntime] = useState({ autoEnabled: false, lastRunAt: "", lastRunStatus: "never", lastChecked: 0, lastError: "" });

  const iconFileInputRef = useRef<HTMLInputElement>(null);
  const dataFileInputRef = useRef<HTMLInputElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const entryToUploadRef = useRef<JobEntry | null>(null);
  const loadedRef = useRef(false);
  const apiSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextApiSaveRef = useRef(false);
  const syncStatusRef = useRef(syncStatus);

  /* ---- computed ---- */
  const countOffers = useMemo(
    () => entries.filter((e) => e.status.toLowerCase() === "offer").length,
    [entries],
  );
  const countInterviews = useMemo(
    () => entries.filter((e) => e.status.includes("面") && !e.status.includes("挂")).length,
    [entries],
  );

  /* ---- effects ---- */

  useEffect(() => {
    syncStatusRef.current = syncStatus;
  }, [syncStatus]);

  // Initial load: API first, fallback to localStorage
  useEffect(() => {
    const load = async () => {
      try {
        const data = await getJobTrackerRecords();
        if (data.records && data.records.length > 0) {
          setEntries(migrateIconPaths(data.records));
          // Also write to localStorage for offline fallback
          trackerStorage.setItem(STORAGE_KEY, JSON.stringify(migrateIconPaths(data.records)));
        } else {
          // Try localStorage
          const saved = trackerStorage.getItem(STORAGE_KEY);
          if (saved) {
            setEntries(migrateIconPaths(JSON.parse(saved)));
          } else {
            setEntries(DEFAULT_ENTRIES);
          }
        }
        setSyncStatus("synced");
      } catch {
        // API unavailable — fall back to localStorage
        try {
          const saved = trackerStorage.getItem(STORAGE_KEY);
          if (saved) {
            setEntries(migrateIconPaths(JSON.parse(saved)));
          } else {
            setEntries(DEFAULT_ENTRIES);
          }
        } catch {
          setEntries(DEFAULT_ENTRIES);
        }
        setSyncStatus("error");
      }
      loadedRef.current = true;
    };
    load();
  }, []);

  // Debounced auto-save to API on data change
  useEffect(() => {
    if (!loadedRef.current) return; // skip initial mount

    // Always write to localStorage immediately
    trackerStorage.setItem(STORAGE_KEY, JSON.stringify(entries));

    // Records pulled from the server are already persisted. Avoid writing them
    // straight back and racing with the background follow-up scheduler.
    if (skipNextApiSaveRef.current) {
      skipNextApiSaveRef.current = false;
      setSyncStatus("synced");
      return;
    }

    // Debounce API save (1s after last change)
    if (apiSaveTimerRef.current) clearTimeout(apiSaveTimerRef.current);
    setSyncStatus("unsaved");
    apiSaveTimerRef.current = setTimeout(async () => {
      try {
        await saveJobTrackerRecords(entries);
        setSyncStatus("synced");
      } catch {
        setSyncStatus("error");
      }
    }, 1000);

    return () => {
      if (apiSaveTimerRef.current) clearTimeout(apiSaveTimerRef.current);
    };
  }, [entries]);

  // Status changes are pushed after manual or scheduled checks. This avoids
  // polling and merges only follow-up fields, preserving local form edits.
  useEffect(() => {
    return subscribeJobTrackerStatusChanges((updates) => {
      const byId = new Map(updates.map((record) => [record.id, record]));
      setEntries((current) => {
        let changed = false;
        const merged = current.map((entry) => {
          const update = byId.get(entry.id);
          if (!update || (
            entry.status === update.status
            && entry.last_checked_at === update.last_checked_at
            && entry.followup_enabled === update.followup_enabled
          )) return entry;
          changed = true;
          return {
            ...entry,
            status: update.status,
            followup_enabled: update.followup_enabled,
            followup_state: update.followup_state,
            last_checked_at: update.last_checked_at,
            last_raw_status: update.last_raw_status,
            last_check_message: update.last_check_message,
            last_parser: update.last_parser,
            last_llm_confidence: update.last_llm_confidence,
            last_llm_tokens: update.last_llm_tokens,
            last_llm_candidate_status: update.last_llm_candidate_status,
            last_llm_candidate_evidence: update.last_llm_candidate_evidence,
            last_llm_application_confidence: update.last_llm_application_confidence,
            last_llm_status_confidence: update.last_llm_status_confidence,
            last_llm_evidence_excerpt: update.last_llm_evidence_excerpt,
            last_application_statuses: update.last_application_statuses,
            last_notification: update.last_notification,
            status_history: update.status_history,
          };
        });
        if (!changed) return current;
        if (syncStatusRef.current === "synced") skipNextApiSaveRef.current = true;
        return merged;
      });
    });
  }, []);

  // Prevent body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = isModalOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isModalOpen]);

  /* ---- form handlers ---- */

  const handleFormChange = useCallback(
    (field: string, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      setFormFeedback(null);
    },
    [],
  );

  const addEntry = useCallback(() => {
    const company = form.company.trim();
    const role = form.role.trim();
    if (!company || !role) {
      setFormFeedback({ type: "error", message: jt.formRequired });
      return;
    }

    const link = form.link.trim();
    const normalizedLink = link && !/^https?:\/\//i.test(link) ? `https://${link}` : link;
    const normalizedForm = {
      ...form,
      company,
      role,
      base: form.base.trim(),
      remark: form.remark.trim(),
      applied_at: form.applied_at,
      link: normalizedLink,
    };
    const icon = detectPresetIcon(company);
    setEntries((prev) => [
      ...prev,
      { id: Date.now(), ...normalizedForm, icon, notes: "" },
    ]);
    setForm(createInitialForm());
    setFormFeedback({ type: "success", message: jt.recordAdded });
  }, [form, jt.formRequired, jt.recordAdded]);

  const updateEntry = useCallback(
    (id: number, field: keyof JobEntry, value: string) => {
      setEntries((prev) =>
        prev.map((e) => (e.id === id ? {
          ...e, [field]: value,
          ...(field === "status" && value.includes("挂") ? { followup_enabled: false } : {}),
        } : e)),
      );
    },
    [],
  );

  const deleteEntry = useCallback((id: number) => {
    if (!window.confirm("确定要删除这条记录吗？")) return;
    setEntries((prev) => prev.filter((e) => e.id !== id));
  }, []);

  useEffect(() => {
    getJobFollowupSchedule().then((schedule) => {
      setFollowupInterval(schedule.interval_hours);
      setFollowupRuntime({ autoEnabled: schedule.auto_enabled, lastRunAt: schedule.last_run_at, lastRunStatus: schedule.last_run_status, lastChecked: schedule.last_checked, lastError: schedule.last_error });
    }).catch(() => {});
  }, []);

  const openFollowup = useCallback((entry: JobEntry) => {
    const host = (() => { try { return new URL(entry.followup_url || entry.link).hostname; } catch { return ""; } })();
    const detected = host.includes("job.byd.com") ? "byd" : host.includes("cmbnt.cmbchina.com") ? "cmb" : host.includes("mokahr.com") ? "moka" : host.includes("jobs.feishu.cn") ? "feishu" : host.includes("zhiye.com") ? "zhiye" : "generic";
    const platform = entry.followup_platform && !(entry.followup_platform === "generic" && detected !== "generic") ? entry.followup_platform : detected;
    setFollowupEntry(entry);
    setFollowupDraft({ enabled: entry.followup_enabled ?? false, aiEnabled: entry.followup_ai_enabled ?? true, platform, url: entry.followup_url || entry.link });
    setFollowupMessage("");
  }, []);

  const persistFollowupDraft = useCallback(async () => {
    if (!followupEntry) return [] as JobEntry[];
    const updated = entries.map((entry) => entry.id === followupEntry.id ? {
      ...entry, followup_enabled: followupDraft.enabled && !entry.status.includes("挂"), followup_ai_enabled: followupDraft.aiEnabled, followup_platform: followupDraft.platform,
      followup_url: followupDraft.url,
    } : entry);
    setEntries(updated);
    await saveJobTrackerRecords(updated);
    return updated;
  }, [entries, followupDraft, followupEntry]);

  const connectFollowup = useCallback(async () => {
    if (!followupEntry || !followupDraft.url) return;
    setFollowupBusy(true);
    try {
      await persistFollowupDraft();
      const result = await connectJobFollowup(followupDraft.platform, followupDraft.url);
      setFollowupMessage(result.message);
    } catch (error: any) {
      setFollowupMessage(error?.response?.data?.detail || error?.message || "连接失败");
    } finally {
      setFollowupBusy(false);
    }
  }, [followupDraft, followupEntry, persistFollowupDraft]);

  const completeFollowup = useCallback(async () => {
    if (!followupEntry) return;
    setFollowupBusy(true);
    try {
      const result = await completeJobFollowupLogin(followupDraft.platform);
      setFollowupMessage(result.message);
      if (result.status === "connected") {
        setEntries((current) => current.map((entry) => entry.id === followupEntry.id ? { ...entry, followup_state: "connected" } : entry));
      }
    } catch (error: any) {
      setFollowupMessage(error?.response?.data?.detail || error?.message || "确认登录失败");
    } finally {
      setFollowupBusy(false);
    }
  }, [followupDraft.platform, followupEntry]);

  const checkFollowup = useCallback(async () => {
    if (!followupEntry) return;
    setFollowupBusy(true);
    try {
      await persistFollowupDraft();
      const result = await checkJobFollowup(followupEntry.id);
      setEntries((current) => current.map((entry) => entry.id === followupEntry.id ? result.record : entry));
      setFollowupEntry(result.record);
      setFollowupMessage(result.message);
    } catch (error: any) {
      setFollowupMessage(error?.response?.data?.detail || error?.message || "检查失败");
    } finally {
      setFollowupBusy(false);
    }
  }, [followupEntry, persistFollowupDraft]);

  const checkAllFollowups = useCallback(async () => {
    setFollowupBusy(true);
    try {
      const result = await checkAllJobFollowups();
      const refreshed = await getJobTrackerRecords();
      setEntries(refreshed.records);
      window.alert(`检查完成：${result.checked} 条自动跟进记录`);
    } catch (error: any) {
      window.alert(error?.response?.data?.detail || error?.message || "自动跟进检查失败");
    } finally {
      setFollowupBusy(false);
    }
  }, []);

  /* ---- icon upload ---- */

  const triggerIconUpload = useCallback((entry: JobEntry) => {
    entryToUploadRef.current = entry;
    iconFileInputRef.current?.click();
  }, []);

  const handleIconUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const inline = window.confirm(
        "提示：\n点击【确认】直接将图片数据内嵌保存到网页(推荐，无需移动文件)；\n点击【取消】则只记录文件名(需确保你已将此图放进 icon/ 文件夹)。",
      );

      if (inline) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const url = ev.target?.result as string;
          if (entryToUploadRef.current) {
            setEntries((prev) =>
              prev.map((e) =>
                e.id === entryToUploadRef.current!.id ? { ...e, icon: url } : e,
              ),
            );
          }
        };
        reader.readAsDataURL(file);
      } else {
        if (entryToUploadRef.current) {
          setEntries((prev) =>
            prev.map((e) =>
              e.id === entryToUploadRef.current!.id
                ? { ...e, icon: "/api/job-tracker/icon/" + file.name }
                : e,
            ),
          );
        }
      }

      e.target.value = "";
      entryToUploadRef.current = null;
    },
    [],
  );

  /* ---- data import / export ---- */

  const triggerDataImport = useCallback(() => {
    dataFileInputRef.current?.click();
  }, []);

  const handleDataImport = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const data = JSON.parse(ev.target?.result as string);
          if (Array.isArray(data)) {
            setEntries(data);
            alert("✅ 存档数据加载成功！");
          } else {
            alert("❌ 格式不正确，解析失败。");
          }
        } catch {
          alert("❌ 无法读取文件，请确认是否为正确的 JSON 存档。");
        }
      };
      reader.readAsText(file);
      e.target.value = "";
    },
    [],
  );

  const exportData = useCallback(() => {
    if (entries.length === 0) {
      alert("暂无数据可供导出！");
      return;
    }
    const blob = new Blob([JSON.stringify(entries, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `job_tracker_data_${new Date().toISOString().split("T")[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [entries]);

  /* ---- notes modal ---- */

  const openNoteModal = useCallback((entry: JobEntry) => {
    setCurrentEntry(entry);
    setTempNotes(entry.notes || "");
    setIsModalOpen(true);
  }, []);

  const closeNoteModal = useCallback(() => {
    setIsModalOpen(false);
    setTimeout(() => {
      setCurrentEntry(null);
      setTempNotes("");
    }, 200);
  }, []);

  const saveNote = useCallback(() => {
    if (currentEntry) {
      setEntries((prev) =>
        prev.map((e) =>
          e.id === currentEntry.id ? { ...e, notes: tempNotes } : e,
        ),
      );
    }
    closeNoteModal();
  }, [currentEntry, tempNotes, closeNoteModal]);

  const exportSingleNote = useCallback(() => {
    if (!currentEntry) return;
    const content = `【${currentEntry.company}】 - ${currentEntry.role}\n状态: ${currentEntry.status}\n批次: ${currentEntry.remark || "无"}\nBase: ${currentEntry.base}\n官网链接: ${currentEntry.link || "无"}\n==========================\n\n${tempNotes}`;
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentEntry.company}_${currentEntry.role}_面经复盘.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }, [currentEntry, tempNotes]);

  /* ---- resizable columns ---- */

  const initResizableColumns = useCallback(() => {
    const table = tableRef.current;
    if (!table) return;

    const resizers = table.querySelectorAll<HTMLDivElement>(".cursor-col-resize");
    resizers.forEach((resizer) => {
      const col = resizer.parentElement as HTMLTableCellElement;
      if (!col) return;

      let startX = 0;
      let startWidth = 0;

      const onMouseMove = (e: MouseEvent) => {
        const width = startWidth + (e.pageX - startX);
        const minWidth = Number(col.dataset.minWidth || 60);
        if (width >= minWidth) col.style.width = `${width}px`;
      };

      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      };

      resizer.addEventListener("mousedown", (e) => {
        startX = e.pageX;
        startWidth = col.offsetWidth;
        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
        e.preventDefault();
      });
    });
  }, []);

  useEffect(() => {
    if (loadedRef.current) {
      // Small delay so the table is rendered
      requestAnimationFrame(initResizableColumns);
    }
  }, [entries.length, initResizableColumns]);

  /* ---- render ---- */

  return (
    <div className="page-enter max-w-[1400px] mx-auto relative">
      {/* Header + Stats */}
      <header className="mb-8 flex flex-col md:flex-row justify-between items-center gap-6">
        <div>
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600 flex items-center gap-3">
            <Rocket className="h-8 w-8 text-indigo-500" />
            {jt.title}
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2 text-sm">
            {jt.subtitle}
          </p>
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <label className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-600 shadow-sm dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"><span>自动跟进间隔</span><select value={followupInterval} onChange={async (event) => { const value = Number(event.target.value); setFollowupInterval(value); try { await saveJobFollowupSchedule(value); setScheduleStatus("已保存"); setTimeout(() => setScheduleStatus(""), 2000); } catch { setScheduleStatus("保存失败"); } }} className="rounded border border-gray-200 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-700"><option value={4}>4 小时</option><option value={6}>6 小时</option><option value={8}>8 小时</option><option value={12}>12 小时</option><option value={24}>24 小时</option></select>{scheduleStatus && <span className={scheduleStatus === "已保存" ? "text-emerald-600" : "text-red-500"}>{scheduleStatus}</span>}</label>
          <div className={`rounded-lg border px-3 py-2 text-xs shadow-sm ${followupRuntime.autoEnabled && followupRuntime.lastRunStatus !== "error" ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300" : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300"}`} title={followupRuntime.lastError || undefined}>{!followupRuntime.autoEnabled ? "自动任务未启用" : followupRuntime.lastRunStatus === "never" ? "自动任务已启动 · 等待首次执行" : followupRuntime.lastRunStatus === "error" ? `自动任务最近执行失败${followupRuntime.lastRunAt ? ` · ${new Date(followupRuntime.lastRunAt).toLocaleString()}` : ""}` : `自动任务正常 · ${new Date(followupRuntime.lastRunAt).toLocaleString()} 检查 ${followupRuntime.lastChecked} 条`}</div>
          <button onClick={() => void checkAllFollowups()} disabled={followupBusy} className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50 dark:border-indigo-800 dark:bg-indigo-950/30 dark:text-indigo-300"><RefreshCw className={`h-4 w-4 ${followupBusy ? "animate-spin" : ""}`} />检查自动跟进</button>
          <div className="flex flex-col gap-2 mr-4">
            <button
              onClick={triggerDataImport}
              className="text-xs px-4 py-1.5 rounded-lg font-medium text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 transition-colors shadow-sm flex items-center justify-center gap-2 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-700"
            >
              <FolderOpen className="h-3.5 w-3.5 text-blue-500" />
              {jt.loadArchive}
            </button>
            <button
              onClick={exportData}
              className="text-xs px-4 py-1.5 rounded-lg font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition-colors shadow-sm flex items-center justify-center gap-2"
            >
              <Download className="h-3.5 w-3.5" />
              {jt.saveArchive}
            </button>
          </div>

          {/* Sync status */}
          <div className="hidden md:flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 mr-2">
            <Server className={`h-3 w-3 ${syncStatus === "loading" ? "animate-pulse text-blue-400" : syncStatus === "synced" ? "text-green-400" : syncStatus === "unsaved" ? "text-amber-400" : "text-red-400"}`} />
            <span className="whitespace-nowrap">
              {syncStatus === "loading" && "加载中..."}
              {syncStatus === "synced" && "已保存至项目文件夹"}
              {syncStatus === "unsaved" && "保存中..."}
              {syncStatus === "error" && "离线模式（仅本地存储）"}
            </span>
          </div>

          <div className="rounded-2xl bg-white/80 dark:bg-gray-800/80 px-5 py-3 shadow-sm border border-gray-200 dark:border-gray-700 text-center">
            <div className="text-gray-500 dark:text-gray-400 text-xs font-semibold uppercase tracking-wider">
              {jt.totalLabel}
            </div>
            <div className="text-xl font-bold text-gray-800 dark:text-white">
              {entries.length}
            </div>
          </div>
          <div className="rounded-2xl bg-white/80 dark:bg-gray-800/80 px-5 py-3 shadow-sm border border-gray-200 dark:border-gray-700 text-center">
            <div className="text-gray-500 dark:text-gray-400 text-xs font-semibold uppercase tracking-wider">
              {jt.interviewingLabel}
            </div>
            <div className="text-xl font-bold text-blue-600 dark:text-blue-400">
              {countInterviews}
            </div>
          </div>
          <div className="rounded-2xl bg-white/80 dark:bg-gray-800/80 px-5 py-3 shadow-sm border border-b-4 border-green-500 dark:border-green-400 text-center">
            <div className="text-gray-500 dark:text-gray-400 text-xs font-semibold uppercase tracking-wider">
              {jt.offersLabel}
            </div>
            <div className="text-xl font-bold text-green-600 dark:text-green-400">
              {countOffers}
            </div>
          </div>
        </div>
      </header>

      {/* Add Form */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm mb-8 dark:border-gray-700 dark:bg-gray-800">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-gray-900 dark:text-white">
          <PlusCircle className="h-5 w-5 text-blue-500" />
          {jt.addRecord}
        </h2>
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            addEntry();
          }}
          className="grid grid-cols-1 md:grid-cols-8 gap-4 items-end"
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {jt.formCompany}
            </label>
            <input
              value={form.company}
              onChange={(e) => handleFormChange("company", e.target.value)}
              aria-required="true"
              aria-invalid={formFeedback?.type === "error" && !form.company.trim()}
              type="text"
              placeholder={jt.formCompanyPlaceholder}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white p-2.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {jt.formRole}
            </label>
            <input
              value={form.role}
              onChange={(e) => handleFormChange("role", e.target.value)}
              aria-required="true"
              aria-invalid={formFeedback?.type === "error" && !form.role.trim()}
              type="text"
              placeholder={jt.formRolePlaceholder}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white p-2.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {jt.formBase}
            </label>
            <input
              value={form.base}
              onChange={(e) => handleFormChange("base", e.target.value)}
              type="text"
              placeholder={jt.formBasePlaceholder}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white p-2.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {jt.formRemark}
            </label>
            <input
              value={form.remark}
              onChange={(e) => handleFormChange("remark", e.target.value)}
              type="text"
              placeholder={jt.formRemarkPlaceholder}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white p-2.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {jt.formAppliedAt}
            </label>
            <input
              value={form.applied_at}
              onChange={(e) => handleFormChange("applied_at", e.target.value)}
              type="datetime-local"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white p-2.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {jt.formLink}
            </label>
            <input
              value={form.link}
              onChange={(e) => handleFormChange("link", e.target.value)}
              type="text"
              inputMode="url"
              placeholder={jt.formLinkPlaceholder}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white p-2.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {jt.formStatus}
            </label>
            <select
              value={form.status}
              onChange={(e) => handleFormChange("status", e.target.value)}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white p-2.5 focus:ring-2 focus:ring-blue-500 outline-none bg-white dark:bg-gray-700 text-sm"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <button
              type="submit"
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center gap-2 shadow-md shadow-blue-200 dark:shadow-blue-900/30 text-sm"
            >
              <Check className="h-4 w-4" />
              {jt.saveRecord}
            </button>
          </div>
          {formFeedback && (
            <p
              role={formFeedback.type === "error" ? "alert" : "status"}
              className={`md:col-span-8 text-sm ${
                formFeedback.type === "error"
                  ? "text-red-600 dark:text-red-400"
                  : "text-green-600 dark:text-green-400"
              }`}
            >
              {formFeedback.message}
            </p>
          )}
        </form>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden dark:border-gray-700 dark:bg-gray-800">
        <div className="overflow-x-auto">
          <table
            ref={tableRef}
            className="w-full text-left border-collapse table-fixed"
          >
            <thead>
              <tr className="bg-gray-50/50 dark:bg-gray-700/50 border-b border-gray-200 dark:border-gray-700">
                <th className="w-12 px-2 py-4 text-center text-sm font-semibold text-gray-600 dark:text-gray-300">
                  {jt.colSequence}
                </th>
                <th className="py-4 px-6 font-semibold text-gray-600 dark:text-gray-300 text-sm relative select-none w-2/12">
                  {jt.colCompany}
                  <div className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize z-10 hover:bg-blue-400/50" />
                </th>
                <th className="py-4 px-6 font-semibold text-gray-600 dark:text-gray-300 text-sm relative select-none w-3/12">
                  {jt.colRole}
                  <div className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize z-10 hover:bg-blue-400/50" />
                </th>
                <th data-min-width="80" className="py-4 px-4 font-semibold text-gray-600 dark:text-gray-300 text-sm relative select-none w-1/12">
                  {jt.colRemark}
                  <div className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize z-10 hover:bg-blue-400/50" />
                </th>
                <th data-min-width="150" className="py-4 px-4 font-semibold text-gray-600 dark:text-gray-300 text-sm relative select-none w-2/12">
                  {jt.colAppliedAt}
                  <div className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize z-10 hover:bg-blue-400/50" />
                </th>
                <th className="py-4 px-6 font-semibold text-gray-600 dark:text-gray-300 text-sm relative select-none w-2/12">
                  {jt.colLink}
                  <div className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize z-10 hover:bg-blue-400/50" />
                </th>
                <th data-min-width="140" className="py-4 px-4 font-semibold text-gray-600 dark:text-gray-300 text-sm relative select-none w-2/12">
                  {jt.colStatus}
                  <div className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize z-10 hover:bg-blue-400/50" />
                </th>
                <th className="py-4 px-6 font-semibold text-gray-600 dark:text-gray-300 text-sm text-center relative select-none w-1/12">
                  {jt.colNotes}
                  <div className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize z-10 hover:bg-blue-400/50" />
                </th>
                <th className="py-4 px-6 font-semibold text-gray-600 dark:text-gray-300 text-sm text-center w-1/12">
                  {jt.colActions}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {entries.map((entry, index) => (
                <tr
                  key={entry.id}
                  className="hover:bg-gray-50/50 dark:hover:bg-gray-700/30 transition-colors group"
                >
                  <td className="px-2 py-4 text-center text-sm font-semibold tabular-nums text-gray-500 dark:text-gray-400">
                    {index + 1}
                  </td>
                  {/* Company */}
                  <td className="py-4 px-6 truncate">
                    <div className="flex items-center gap-3 overflow-hidden">
                      <div
                        className="relative group/avatar cursor-pointer shrink-0"
                        onClick={() => triggerIconUpload(entry)}
                        title={jt.clickChangeIcon}
                      >
                        {entry.icon ? (
                          <img
                            src={entry.icon}
                            className="w-10 h-10 rounded-xl object-cover shadow-sm border border-gray-100 bg-white dark:border-gray-600"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display =
                                "none";
                              const fallback =
                                (e.target as HTMLImageElement)
                                  .nextElementSibling;
                              if (fallback) {
                                (fallback as HTMLElement).style.display =
                                  "flex";
                              }
                            }}
                            alt=""
                          />
                        ) : null}
                        <div
                          className={`w-10 h-10 rounded-xl items-center justify-center text-white font-bold shadow-sm shrink-0 ${getAvatarColor(entry.company)} ${entry.icon ? "hidden" : "flex"}`}
                        >
                          {entry.company.charAt(0).toUpperCase()}
                        </div>
                        <div className="absolute inset-0 bg-slate-900/50 rounded-xl opacity-0 group-hover/avatar:opacity-100 transition-opacity flex items-center justify-center text-white text-[10px]">
                          <ImageIcon className="h-4 w-4" />
                        </div>
                      </div>
                      <input
                        value={entry.company}
                        onChange={(e) =>
                          updateEntry(entry.id, "company", e.target.value)
                        }
                        className="bg-transparent border-b border-transparent hover:border-gray-300 focus:border-blue-500 outline-none transition-all font-bold text-gray-800 dark:text-white text-base pr-2 w-full truncate"
                        placeholder={jt.formCompanyPlaceholder}
                      />
                    </div>
                  </td>

                  {/* Role & Base */}
                  <td className="py-4 px-6 truncate">
                    <input
                      value={entry.role}
                      onChange={(e) =>
                        updateEntry(entry.id, "role", e.target.value)
                      }
                      className="bg-transparent border-b border-transparent hover:border-gray-300 focus:border-blue-500 outline-none transition-all font-medium text-gray-700 dark:text-gray-200 pr-4 w-full"
                      placeholder={jt.formRolePlaceholder}
                    />
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 flex items-center gap-1">
                      <MapPin className="h-3 w-3 text-gray-400" />
                      <input
                        value={entry.base}
                        onChange={(e) =>
                          updateEntry(entry.id, "base", e.target.value)
                        }
                        className="bg-transparent border-b border-transparent hover:border-gray-300 focus:border-blue-500 outline-none transition-all w-full"
                        placeholder={jt.formBasePlaceholder}
                      />
                    </div>
                  </td>

                  {/* Remark */}
                  <td className="py-4 px-4 truncate">
                    <div className="flex items-center">
                      <Tag className="h-3 w-3 text-gray-300 mr-2 shrink-0" />
                      <input
                        value={entry.remark}
                        onChange={(e) =>
                          updateEntry(entry.id, "remark", e.target.value)
                        }
                        placeholder={jt.formRemarkPlaceholder}
                        className="bg-transparent border-b border-transparent hover:border-gray-300 focus:border-blue-500 outline-none transition-all text-sm text-gray-700 dark:text-gray-200 font-medium w-full"
                      />
                    </div>
                  </td>

                  {/* Applied at */}
                  <td className="py-4 px-4">
                    <input
                      value={entry.applied_at || ""}
                      onChange={(e) =>
                        updateEntry(entry.id, "applied_at", e.target.value)
                      }
                      type="datetime-local"
                      className="w-full min-w-0 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-blue-500 outline-none transition-all text-xs text-gray-600 dark:text-gray-300"
                      aria-label={jt.colAppliedAt}
                    />
                  </td>

                  {/* Link */}
                  <td className="py-4 px-6 truncate">
                    <div className="flex items-center gap-2 overflow-hidden">
                      {entry.link && (
                        <a
                          href={entry.link}
                          target="_blank"
                          rel="noreferrer"
                          className="text-blue-500 hover:text-blue-700 transition-colors shrink-0"
                          title={jt.gotoWebsite}
                        >
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                      <input
                        value={entry.link}
                        onChange={(e) =>
                          updateEntry(entry.id, "link", e.target.value)
                        }
                        placeholder={jt.noLink}
                        className="bg-transparent border-b border-transparent hover:border-gray-300 focus:border-blue-500 outline-none transition-all text-xs text-gray-600 dark:text-gray-400 w-full"
                      />
                    </div>
                  </td>

                  {/* Status */}
                  <td className="py-4 px-4">
                    <select
                      value={entry.status}
                      onChange={(e) =>
                        updateEntry(entry.id, "status", e.target.value)
                      }
                      className={`text-sm font-semibold rounded-full px-3 py-1.5 border-0 outline-none appearance-none cursor-pointer w-full text-center ${getStatusClass(entry.status)}`}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </td>

                  {/* Notes */}
                  <td className="py-4 px-6 text-center">
                    <button
                      onClick={() => openNoteModal(entry)}
                      className={`inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors w-full ${
                        entry.notes
                          ? "bg-indigo-50 text-indigo-600 hover:bg-indigo-100 dark:bg-indigo-900/20 dark:text-indigo-300 dark:hover:bg-indigo-900/30"
                          : "bg-gray-50 text-gray-500 hover:bg-gray-100 dark:bg-gray-700 dark:text-gray-400 dark:hover:bg-gray-600"
                      }`}
                    >
                      {entry.notes ? (
                        <>
                          <BookOpen className="h-4 w-4" />
                          <span>{jt.viewNotes}</span>
                        </>
                      ) : (
                        <>
                          <PenSquare className="h-4 w-4" />
                          <span>{jt.addNotes}</span>
                        </>
                      )}
                    </button>
                  </td>

                  {/* Actions */}
                  <td className="py-4 px-6 text-center">
                    <div className="flex items-center justify-center gap-1"><button onClick={() => openFollowup(entry)} className={`rounded-lg p-2 transition-colors ${entry.followup_enabled ? "bg-emerald-50 text-emerald-600 hover:bg-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-300" : "text-gray-400 hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-indigo-950/30"}`} title={entry.followup_enabled ? `自动跟进：${entry.followup_state || "待连接"}` : "设置自动跟进"}><ShieldCheck className="h-4 w-4" /></button><button
                      onClick={() => deleteEntry(entry.id)}
                      className="text-gray-400 hover:text-red-500 transition-colors p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 opacity-0 group-hover:opacity-100"
                      title={jt.deleteAction}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button></div>
                  </td>
                </tr>
              ))}

              {entries.length === 0 && (
                <tr>
                  <td
                    colSpan={9}
                    className="py-12 text-center text-gray-400 dark:text-gray-500"
                  >
                    <FolderOpen className="h-10 w-10 mx-auto mb-3 opacity-50" />
                    <p>{jt.noData}</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Hidden file inputs */}
      <input
        ref={iconFileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleIconUpload}
      />
      <input
        ref={dataFileInputRef}
        type="file"
        accept=".json"
        className="hidden"
        onChange={handleDataImport}
      />

      {/* Automatic follow-up modal */}
      {followupEntry && <div className="fixed inset-0 z-50 flex items-center justify-center p-4"><div className="absolute inset-0 bg-slate-900/45 backdrop-blur-sm" onClick={() => setFollowupEntry(null)} /><div className="relative z-10 max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl dark:bg-gray-800">
        <div className="flex items-start justify-between border-b border-gray-100 px-5 py-4 dark:border-gray-700"><div><h3 className="flex items-center gap-2 text-lg font-bold text-gray-900 dark:text-white"><ShieldCheck className="h-5 w-5 text-emerald-500" />自动跟进 · {followupEntry.company}</h3><p className="mt-1 text-xs text-gray-500">使用本地独立 Chrome 会话；不保存密码，不绕过验证码。</p></div><button onClick={() => setFollowupEntry(null)} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"><X className="h-5 w-5" /></button></div>
        <div className="space-y-4 p-5">
          <label className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900"><span><span className="block text-sm font-medium text-gray-800 dark:text-gray-100">启用定时自动跟进</span><span className="text-xs text-gray-500">{followupEntry.status.includes("挂") ? "已淘汰，自动跟进已关闭；如需恢复，请先修改当前状态。" : "按求职记录页顶部选择的间隔检查；默认每 8 小时（04:00、12:00、20:00）"}</span></span><input type="checkbox" checked={followupDraft.enabled && !followupEntry.status.includes("挂")} disabled={followupEntry.status.includes("挂")} onChange={(event) => setFollowupDraft((current) => ({ ...current, enabled: event.target.checked }))} className="h-4 w-4 disabled:opacity-50" /></label>
          <label className="flex items-center justify-between rounded-lg border border-indigo-100 bg-indigo-50/60 px-3 py-2 dark:border-indigo-900 dark:bg-indigo-950/20"><span><span className="block text-sm font-medium text-gray-800 dark:text-gray-100">使用 AI 语义识别岗位与状态</span><span className="text-xs text-gray-500">AI 直接判断页面中有几个岗位、岗位名称和各自状态；本地仅保留明确规则、原文核验与安全兜底，相同页面优先走缓存</span></span><input type="checkbox" checked={followupDraft.aiEnabled} onChange={(event) => setFollowupDraft((current) => ({ ...current, aiEnabled: event.target.checked }))} className="h-4 w-4" /></label>
          <div className="grid gap-3 sm:grid-cols-3"><label className="text-xs text-gray-600 dark:text-gray-300"><span className="mb-1 block font-medium">招聘平台</span><select value={followupDraft.platform} onChange={(event) => setFollowupDraft((current) => ({ ...current, platform: event.target.value }))} className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-white"><option value="byd">比亚迪招聘</option><option value="cmb">招商银行招聘</option><option value="moka">Moka</option><option value="feishu">飞书招聘</option><option value="zhiye">zhiye.com</option><option value="generic">其他网站</option></select></label><label className="text-xs text-gray-600 dark:text-gray-300 sm:col-span-2"><span className="mb-1 block font-medium">投递中心/个人中心链接</span><input value={followupDraft.url} onChange={(event) => setFollowupDraft((current) => ({ ...current, url: event.target.value }))} placeholder="请填写能看到投递状态的个人中心链接" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label></div>
          <div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-300">连接状态：{followupEntry.followup_state || "not_connected"}</span>{followupEntry.last_checked_at && <span className="text-xs text-gray-500">上次检查：{new Date(followupEntry.last_checked_at).toLocaleString()}</span>}{followupEntry.last_raw_status && <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">网站原文：{followupEntry.last_raw_status}</span>}{followupEntry.last_parser && <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs text-violet-700 dark:bg-violet-950/30 dark:text-violet-300">识别方式：{followupEntry.last_parser === "llm" ? "AI 兜底" : followupEntry.last_parser === "local" ? "本地规则" : "未识别"}</span>}{followupEntry.last_llm_candidate_status && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">AI 候选：{followupEntry.last_llm_candidate_status} · {followupEntry.last_llm_candidate_evidence || "无证据"}</span>}{followupEntry.last_llm_confidence != null && <span className="text-xs text-gray-500">综合 {Math.round(followupEntry.last_llm_confidence * 100)}% · 岗位 {Math.round((followupEntry.last_llm_application_confidence || 0) * 100)}% · 状态 {Math.round((followupEntry.last_llm_status_confidence || 0) * 100)}% · 本次 {followupEntry.last_llm_tokens || 0} tokens</span>}</div>
          {followupEntry.last_llm_evidence_excerpt && <div className="rounded-lg border border-amber-100 bg-amber-50/60 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-200"><span className="font-semibold">AI 复核片段：</span>{followupEntry.last_llm_evidence_excerpt}</div>}
          {(followupEntry.last_application_statuses || []).length > 0 && <div className="space-y-2 rounded-lg border border-gray-100 p-3 dark:border-gray-700"><div className="text-xs font-semibold text-gray-700 dark:text-gray-200">并行投递明细</div>{(followupEntry.last_application_statuses || []).map((application, index) => <div key={`${application.role}-${index}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-gray-50 px-3 py-2 text-xs dark:bg-gray-900"><div><span className="font-medium text-gray-800 dark:text-gray-100">{application.role}</span><span className="ml-2 text-gray-500">原文：{application.raw_status || "未识别"}</span></div><div className="flex items-center gap-2"><span className={`rounded-full px-2 py-0.5 ${application.accepted ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300" : "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"}`}>{application.status === "unknown" ? "待核实" : application.status}</span><span className="text-gray-500">岗位 {Math.round(application.application_match_confidence * 100)}% · {application.status_inferred_by_rule ? "投递记录规则确认" : `状态 ${Math.round(application.status_confidence * 100)}%`}</span></div></div>)}</div>}
          {followupMessage && <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">{followupMessage}</div>}
          <div className="flex flex-wrap gap-2"><button onClick={() => void connectFollowup()} disabled={followupBusy || !followupDraft.url} className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"><LogIn className="h-4 w-4" />普通 Chrome 登录</button><button onClick={() => void completeFollowup()} disabled={followupBusy} className="rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 dark:border-gray-600 dark:text-gray-300">关闭登录窗口后确认</button><button onClick={() => void checkFollowup()} disabled={followupBusy || !followupDraft.url} className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300 px-3 py-2 text-sm font-medium text-emerald-700 disabled:opacity-50 dark:border-emerald-800 dark:text-emerald-300">{followupBusy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}立即检查</button><button onClick={async () => { await persistFollowupDraft(); setFollowupMessage("自动跟进设置已保存"); }} disabled={followupBusy} className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white"><Save className="h-4 w-4" />保存设置</button></div>
          <div className="border-t border-gray-100 pt-4 dark:border-gray-700"><h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100"><History className="h-4 w-4" />状态时间线</h4>{(followupEntry.status_history || []).length === 0 ? <p className="text-sm text-gray-400">尚未检测到状态变化。</p> : <div className="space-y-3">{[...(followupEntry.status_history || [])].reverse().map((event, index) => <div key={`${event.checked_at}-${index}`} className="border-l-2 border-indigo-200 pl-3 dark:border-indigo-800"><div className="text-sm font-medium text-gray-800 dark:text-gray-100">{event.status}</div><div className="text-xs text-gray-500">{new Date(event.checked_at).toLocaleString()} · {event.raw_status || "网站状态"}</div>{event.evidence_url && <a href={event.evidence_url} target="_blank" rel="noreferrer" className="text-xs text-blue-500 hover:underline">查看检查页面</a>}</div>)}</div>}</div>
        </div>
      </div></div>}

      {/* Notes Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
            onClick={closeNoteModal}
          />
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-3xl relative z-10 flex flex-col h-[85vh]">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-700/50 rounded-t-2xl">
              <div>
                <h3 className="font-bold text-lg text-gray-800 dark:text-white flex items-center gap-2">
                  <BookMarked className="h-5 w-5 text-indigo-500" />
                  {jt.notesTitle}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {jt.editingLabel}
                  <span className="font-semibold text-gray-700 dark:text-gray-200">
                    {currentEntry?.company}
                  </span>{" "}
                  - {currentEntry?.role}
                </p>
              </div>
              <button
                onClick={closeNoteModal}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-2 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Textarea */}
            <div className="p-6 flex-1 flex flex-col overflow-hidden bg-gray-50/50 dark:bg-gray-900/30">
              <textarea
                value={tempNotes}
                onChange={(e) => setTempNotes(e.target.value)}
                className="w-full flex-1 p-5 border border-gray-200 dark:border-gray-600 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none resize-none bg-white dark:bg-gray-800 dark:text-white transition-colors text-sm leading-relaxed shadow-inner"
                placeholder={jt.notesPlaceholder}
              />
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50 rounded-b-2xl flex justify-between items-center">
              {currentEntry?.notes ? (
                <button
                  onClick={exportSingleNote}
                  className="text-xs text-gray-600 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 font-medium flex items-center gap-1.5 px-3 py-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600"
                >
                  <FileDown className="h-3.5 w-3.5" />
                  {jt.exportNote}
                </button>
              ) : (
                <div />
              )}
              <div className="flex gap-3">
                <button
                  onClick={closeNoteModal}
                  className="px-5 py-2 rounded-lg font-medium text-gray-600 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                >
                  {jt.cancel}
                </button>
                <button
                  onClick={saveNote}
                  className="px-5 py-2 rounded-lg font-medium text-white bg-blue-600 hover:bg-blue-700 shadow-md shadow-blue-200 dark:shadow-blue-900/30 transition-colors flex items-center gap-2"
                >
                  <Save className="h-4 w-4" />
                  {jt.saveNote}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
