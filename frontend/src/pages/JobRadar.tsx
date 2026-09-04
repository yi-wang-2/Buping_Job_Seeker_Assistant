import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BriefcaseBusiness, Building2, Check, Clock3, ExternalLink, Filter, Heart, LoaderCircle,
  MapPin, Radar, RefreshCw, Save, Search, Settings2, Sparkles, Target, ThumbsDown, Upload, WandSparkles, X,
} from "lucide-react";
import type { Strings } from "../i18n";
import {
  getCachedLinkedJobs, getDailyJobRecommendations, getJobPreferences, getJobRadarRecommendations, getJobRadarStats, getLinkedJobRecommendations,
  importJobRadarFile, saveJobPreferences, syncJobRadarUrl, trackRecommendedJob, updateJobRadarAction,
  type JobPreferences, type JobRadarStats, type JobRecommendation, type LinkedJobRecommendation,
} from "../api/client";

const DEFAULT_SOURCE = "https://docs.qq.com/smartsheet/DZkdPVGtGb1ZvaG5R?tab=t00i2h";
const FEISHU_SOURCE = "https://yal2at57cvq.feishu.cn/base/GtSLbyyR3aCENOsJYC6cdlsVnih?from=from_copylink";
type JobScene = "general" | "state_owned" | "civil_service";
const DEFAULT_PREFERENCES: JobPreferences = {
  target_roles: [], preferred_locations: [], acceptable_locations: [], excluded_locations: [],
  recruitment_types: [], industries: [], company_types: [], preferred_keywords: [],
  excluded_keywords: [], company_blacklist: [],
  weights: { skills: 25, role: 25, location: 15, industry: 10, company: 10, recruitment: 10, referral: 5 },
};

export default function JobRadarPage({ t }: { t: Strings }) {
  const english = t.nav.settings === "Settings";
  const [sourceUrl, setSourceUrl] = useState(DEFAULT_SOURCE);
  const [scene, setScene] = useState<JobScene>("general");
  const [items, setItems] = useState<JobRecommendation[]>([]);
  const [dailyItems, setDailyItems] = useState<JobRecommendation[]>([]);
  const [stats, setStats] = useState<JobRadarStats>({ total: 0, companies: 0, favorites: 0, by_scene: { general: 0, state_owned: 0, civil_service: 0 }, schedule: { source_url: DEFAULT_SOURCE, source_urls: [DEFAULT_SOURCE, FEISHU_SOURCE], auto_sync: true, auto_sync_time: "06:00" }, last_sync: null });
  const [profile, setProfile] = useState({ preferred_roles: [] as string[], preferred_locations: [] as string[], resume_skills: [] as string[] });
  const [query, setQuery] = useState("");
  const [minScore, setMinScore] = useState(40);
  const [companyType, setCompanyType] = useState("");
  const [matchLevel, setMatchLevel] = useState("");
  const [recruitmentType, setRecruitmentType] = useState("");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [preferences, setPreferences] = useState<JobPreferences>(DEFAULT_PREFERENCES);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState("");
  const [tracked, setTracked] = useState<Record<string, boolean>>({});
  const [trackingJob, setTrackingJob] = useState<JobRecommendation | null>(null);
  const [trackDraft, setTrackDraft] = useState({ company: "", role: "", base: "", recruitment_type: "", link: "", notes: "" });
  const [savingTrack, setSavingTrack] = useState(false);
  const [linkedJobs, setLinkedJobs] = useState<Record<string, LinkedJobRecommendation[]>>({});
  const [loadingLinkedJobs, setLoadingLinkedJobs] = useState<Record<string, boolean>>({});
  const [linkedJobErrors, setLinkedJobErrors] = useState<Record<string, string>>({});
  const [linkedJobCounts, setLinkedJobCounts] = useState<Record<string, number>>({});
  const [showingAllLinkedJobs, setShowingAllLinkedJobs] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [recommendations, daily, radarStats] = await Promise.all([
        getJobRadarRecommendations({ minScore, query, limit: 200, companyType, matchLevel, recruitmentType, favoriteOnly, scene }),
        getDailyJobRecommendations(scene), getJobRadarStats(),
      ]);
      setItems(recommendations.items);
      setDailyItems(daily.items);
      const loadedJobs = [...recommendations.items, ...daily.items];
      setLinkedJobs(Object.fromEntries(loadedJobs.filter((job) => job.linked_jobs?.length).map((job) => [job.id, job.linked_jobs])));
      setLinkedJobCounts(Object.fromEntries(loadedJobs.map((job) => [job.id, job.linked_job_count || 0])));
      setProfile(recommendations.profile);
      setStats(radarStats);
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || (english ? "Load failed" : "加载失败"));
    } finally {
      setLoading(false);
    }
  }, [companyType, english, favoriteOnly, matchLevel, minScore, query, recruitmentType, scene]);

  useEffect(() => {
    const timer = window.setTimeout(load, 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    getJobPreferences().then(setPreferences).catch(() => undefined);
  }, []);

  const sync = async () => {
    setSyncing(true);
    setMessage(english ? "Reading the read-only sheet in local Chrome..." : "正在通过本地 Chrome 读取只读表格，请稍候……");
    try {
      const result = await syncJobRadarUrl(sourceUrl);
      setMessage(english
        ? `Synced ${result.imported}: ${result.created} new, ${result.updated} changed.`
        : `同步 ${result.imported} 条：新增 ${result.created} 条，更新 ${result.updated} 条。`);
      await load();
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || (english ? "Sync failed" : "同步失败"));
    } finally {
      setSyncing(false);
    }
  };

  const importFallback = async (file?: File) => {
    if (!file) return;
    setSyncing(true);
    try {
      const result = await importJobRadarFile(file, sourceUrl);
      setMessage(english ? `Imported ${result.imported} jobs.` : `已导入 ${result.imported} 条岗位。`);
      await load();
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || (english ? "Import failed" : "导入失败"));
    } finally {
      setSyncing(false);
    }
  };

  const track = (job: JobRecommendation) => {
    setTrackingJob(job);
    setTrackDraft({
      company: job.company,
      role: job.role || "招聘岗位",
      base: job.location,
      recruitment_type: job.recruitment_type,
      link: job.link,
      notes: [job.industry, job.description, job.referral].filter(Boolean).join("\n"),
    });
  };

  const confirmTrack = async () => {
    if (!trackingJob) return;
    setSavingTrack(true);
    try {
      const result = await trackRecommendedJob(trackingJob.id, trackDraft);
      setTracked((current) => ({ ...current, [trackingJob.id]: true }));
      setTrackingJob(null);
      await load();
      setMessage(result.status === "exists"
        ? (english ? "Already in Job Tracker." : "该岗位已在求职记录中。")
        : result.status === "updated"
          ? (english ? "Job Tracker entry updated." : "已用确认后的信息更新求职记录。")
          : (english ? "Added to Job Tracker." : "已加入求职记录。"));
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || (english ? "Failed to add" : "添加失败"));
    } finally {
      setSavingTrack(false);
    }
  };

  const updateAction = async (job: JobRecommendation, action: "favorite" | "not_interested") => {
    try {
      const enabled = action === "favorite" ? !job.favorite : !job.not_interested;
      await updateJobRadarAction(job.id, action, enabled);
      setMessage(action === "favorite"
        ? (enabled ? "已收藏该企业" : "已取消收藏")
        : (enabled ? "已标记为不感兴趣" : "已撤销不感兴趣"));
      await load();
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || "操作失败");
    }
  };

  const updatePreferenceList = (field: keyof JobPreferences, value: string) => {
    setPreferences((current) => ({ ...current, [field]: value.split(/[，,]/).map((item) => item.trim()) }));
  };

  const togglePreference = (field: "recruitment_types" | "company_types", value: string) => {
    setPreferences((current) => ({
      ...current,
      [field]: current[field].includes(value) ? current[field].filter((item) => item !== value) : [...current[field], value],
    }));
  };

  const savePreferences = async () => {
    setSavingPreferences(true);
    try {
      const cleaned = Object.fromEntries(Object.entries(preferences).map(([key, value]) => [key, Array.isArray(value) ? value.filter(Boolean) : value])) as unknown as JobPreferences;
      const result = await saveJobPreferences(cleaned);
      setPreferences(result.preferences);
      setMessage("求职偏好已保存，推荐分数已重新计算");
      await load();
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || "求职偏好保存失败");
    } finally {
      setSavingPreferences(false);
    }
  };

  const highMatches = useMemo(() => items.filter((item) => item.score >= 70).length, [items]);

  const loadLinkedJobs = async (job: JobRecommendation) => {
    setLoadingLinkedJobs((current) => ({ ...current, [job.id]: true }));
    setLinkedJobErrors((current) => ({ ...current, [job.id]: "" }));
    try {
      const result = await getLinkedJobRecommendations(job.id);
      setLinkedJobs((current) => ({ ...current, [job.id]: result.items }));
      setLinkedJobCounts((current) => ({ ...current, [job.id]: result.count }));
      setShowingAllLinkedJobs((current) => ({ ...current, [job.id]: false }));
      if (!result.items.length) {
        setLinkedJobErrors((current) => ({ ...current, [job.id]: result.diagnostics?.reason || (english ? "No concrete job descriptions were found on this page." : "该页面暂未识别到具体岗位与 JD。") }));
      } else if (result.status === "busy") {
        setLinkedJobErrors((current) => ({ ...current, [job.id]: result.diagnostics?.reason || "后台正在刷新其他企业，当前显示本地缓存。" }));
      } else if (result.status === "partial") {
        setLinkedJobErrors((current) => ({ ...current, [job.id]: result.diagnostics?.reason || "仅提取到部分岗位，已按现有结果排序。" }));
      }
    } catch (error: any) {
      setLinkedJobErrors((current) => ({
        ...current,
        [job.id]: error?.response?.data?.detail || error?.message || (english ? "Failed to read job details" : "岗位详情读取失败"),
      }));
    } finally {
      setLoadingLinkedJobs((current) => ({ ...current, [job.id]: false }));
    }
  };

  const loadAllLinkedJobs = async (job: JobRecommendation) => {
    setLoadingLinkedJobs((current) => ({ ...current, [job.id]: true }));
    try {
      const result = await getCachedLinkedJobs(job.id);
      setLinkedJobs((current) => ({ ...current, [job.id]: result.items }));
      setLinkedJobCounts((current) => ({ ...current, [job.id]: result.count }));
      setShowingAllLinkedJobs((current) => ({ ...current, [job.id]: true }));
    } catch (error: any) {
      setLinkedJobErrors((current) => ({ ...current, [job.id]: error?.response?.data?.detail || error?.message || "本地岗位读取失败" }));
    } finally {
      setLoadingLinkedJobs((current) => ({ ...current, [job.id]: false }));
    }
  };

  const renderJobCard = (job: JobRecommendation, featured = false) => (
    <article key={job.id} className={`rounded-2xl border bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md dark:bg-gray-800 ${featured ? "border-amber-300 dark:border-amber-700" : "border-gray-200 dark:border-gray-700"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><span className="text-lg font-bold text-brand-600">{job.company}</span><span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-700 dark:text-gray-300">{job.company_type}</span><span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">{job.match_level}</span></div>
          <h3 className={`mt-1 ${job.role ? "text-base font-semibold text-gray-800 dark:text-gray-100" : "text-xs font-normal text-gray-400 dark:text-gray-500"}`}>{job.role || (english ? "Open positions" : "招聘岗位")}</h3>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">{job.location && <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{job.location}</span>}{job.industry && <span className="rounded bg-sky-50 px-2 py-0.5 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">{job.industry}</span>}{job.recruitment_tags.map((tag) => <span key={tag} className="rounded bg-violet-50 px-2 py-0.5 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">{tag}</span>)}{job.recruitment_type && job.recruitment_tags.length === 0 && <span>{job.recruitment_type}</span>}</div>
        </div>
        <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-lg font-bold ${job.score >= 70 ? "bg-emerald-100 text-emerald-700" : job.score >= 50 ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-600"}`}>{job.score}</div>
      </div>

      <div className="mt-4 space-y-2">{job.reasons.map((reason) => <div key={reason} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300"><Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />{reason}</div>)}{job.hard_risks.map((risk) => <div key={risk} className="text-sm text-red-600">⚠ {risk}</div>)}</div>
      {job.referral && <div className="mt-3 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700 dark:bg-brand-950/30 dark:text-brand-300"><span className="font-medium">内推码：</span>{job.referral}</div>}
      {job.description && <details className="mt-3 rounded-lg border border-gray-100 px-3 py-2 text-sm dark:border-gray-700"><summary className="cursor-pointer font-medium text-gray-700 dark:text-gray-200">查看招聘原文</summary><div className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap break-words text-gray-600 dark:text-gray-300">{job.description}</div></details>}
      {job.link && <div className="mt-3">
        <button type="button" onClick={() => void loadLinkedJobs(job)} disabled={loadingLinkedJobs[job.id]} className="inline-flex items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300">
          {loadingLinkedJobs[job.id] ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Target className="h-3.5 w-3.5" />}
          {loadingLinkedJobs[job.id] ? (english ? "Refreshing jobs..." : "正在刷新岗位……") : (linkedJobs[job.id]?.length ? (english ? "Refresh jobs" : "刷新岗位") : (english ? "Crawl jobs" : "抓取岗位到本地"))}
        </button>
        {linkedJobErrors[job.id] && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{linkedJobErrors[job.id]}</p>}
        {linkedJobs[job.id]?.length > 0 && <div className="mt-3 space-y-3">
          <div className="flex items-center justify-between gap-2"><div className="text-xs font-semibold text-gray-500">{showingAllLinkedJobs[job.id] ? `全部匹配岗位（${linkedJobCounts[job.id] || linkedJobs[job.id].length}）` : (english ? "Top 3 jobs stored locally" : "本地岗位库中最匹配的 3 个岗位")}</div>{!showingAllLinkedJobs[job.id] && (linkedJobCounts[job.id] || 0) > 3 && <button type="button" onClick={() => void loadAllLinkedJobs(job)} className="text-xs font-medium text-brand-600 hover:underline">查看全部 {linkedJobCounts[job.id]} 个岗位</button>}{showingAllLinkedJobs[job.id] && <button type="button" onClick={() => { setLinkedJobs((current) => ({ ...current, [job.id]: current[job.id].slice(0, 3) })); setShowingAllLinkedJobs((current) => ({ ...current, [job.id]: false })); }} className="text-xs font-medium text-brand-600 hover:underline">仅看 Top 3</button>}</div>
          {linkedJobs[job.id].map((linked, index) => <div key={`${linked.link}-${linked.role}`} className="rounded-xl border border-brand-100 bg-brand-50/40 p-3 dark:border-brand-900 dark:bg-brand-950/20">
            <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="text-sm font-semibold text-gray-800 dark:text-gray-100"><span className="mr-2 text-brand-600">#{index + 1}</span>{linked.role}</div>{linked.location && <div className="mt-1 text-xs text-gray-500">{linked.location}</div>}</div><span className="rounded-lg bg-emerald-100 px-2 py-1 text-xs font-bold text-emerald-700">{linked.score}</span></div>
            <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">{linked.reasons.slice(0, 2).join(" · ")}</div>
            <details className="mt-2 text-xs"><summary className="cursor-pointer font-medium text-brand-700 dark:text-brand-300">{english ? "View JD" : "查看 JD"}</summary><div className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap break-words text-gray-600 dark:text-gray-300">{linked.description}</div></details>
            <a href={linked.link} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"><ExternalLink className="h-3 w-3" />{english ? "Open job" : "打开岗位详情"}</a>
          </div>)}
        </div>}
      </div>}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 pt-4 dark:border-gray-700"><div className="text-[11px] text-gray-400">{english ? "Source updated" : "更新时间"} {job.source_updated_at || (english ? "Not provided" : "原表未提供")}</div><div className="flex flex-wrap gap-2"><button onClick={() => updateAction(job, "favorite")} className={`inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs ${job.favorite ? "border-rose-300 bg-rose-50 text-rose-600" : "border-gray-200 text-gray-600 dark:border-gray-600 dark:text-gray-300"}`}><Heart className={`h-3.5 w-3.5 ${job.favorite ? "fill-current" : ""}`} />{job.favorite ? "已收藏" : "收藏"}</button><button onClick={() => updateAction(job, "not_interested")} className={`inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs ${job.not_interested ? "border-gray-400 bg-gray-100 text-gray-700" : "border-gray-200 text-gray-600 dark:border-gray-600 dark:text-gray-300"}`}><ThumbsDown className="h-3.5 w-3.5" />{job.not_interested ? "已标记" : "不感兴趣"}</button>{job.link && <a href={job.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-2 text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300"><ExternalLink className="h-3.5 w-3.5" />查看</a>}<button onClick={() => track(job)} disabled={tracked[job.id] || job.applied} className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-2 text-xs font-semibold text-white hover:bg-brand-700 disabled:bg-emerald-600">{tracked[job.id] || job.applied ? <Check className="h-3.5 w-3.5" /> : <WandSparkles className="h-3.5 w-3.5" />}{tracked[job.id] || job.applied ? "已投递/记录" : "加入求职记录"}</button></div></div>
    </article>
  );
  const fmtTime = (value?: string) => value ? new Date(value).toLocaleString() : (english ? "Never" : "尚未同步");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-3 text-2xl font-bold text-gray-900 dark:text-white">
            <Radar className="h-7 w-7 text-brand-600" />{english ? "Job Radar" : "岗位雷达"}
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setFavoriteOnly((value) => !value)} className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${favoriteOnly ? "border-rose-300 bg-rose-50 text-rose-600 dark:bg-rose-950/30" : "border-gray-200 bg-white text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200"}`}><Heart className={`h-4 w-4 ${favoriteOnly ? "fill-current" : ""}`} />收藏夹 <span className="rounded-full bg-white/70 px-1.5 text-xs dark:bg-gray-900/50">{stats.favorites}</span></button>
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
            {english ? "Local scoring · No LLM tokens" : "本地评分 · 0 LLM Token"}
          </div>
        </div>
      </div>

      <div className="grid gap-2 rounded-xl border border-gray-200 bg-white p-2 shadow-sm sm:grid-cols-3 dark:border-gray-700 dark:bg-gray-800">
        {([
          ["general", "普通招聘", "企业校招、实习和社会招聘"],
          ["state_owned", "央国企招聘", "央企、国企与事业单位"],
          ["civil_service", "考公考编", "信息源待接入"],
        ] as const).map(([value, label, description]) => <button key={value} type="button" onClick={() => setScene(value)} className={`rounded-lg px-4 py-3 text-left transition ${scene === value ? "bg-brand-600 text-white shadow-sm" : "hover:bg-gray-50 dark:hover:bg-gray-700"}`}><div className="flex items-center justify-between gap-2"><span className="font-semibold">{label}</span><span className={`rounded-full px-2 py-0.5 text-xs ${scene === value ? "bg-white/20" : "bg-gray-100 text-gray-500 dark:bg-gray-900"}`}>{stats.by_scene[value] || 0}</span></div><div className={`mt-1 text-xs ${scene === value ? "text-brand-100" : "text-gray-500"}`}>{description}</div></button>)}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100"><span className="flex items-center gap-2"><RefreshCw className="h-4 w-4 text-brand-600" />{english ? "Read-only source sync" : "岗位源"}</span><span className="text-xs font-normal text-gray-500">每天 {stats.schedule.auto_sync_time} 自动同步</span></div>
        <div className="flex flex-col gap-2 lg:flex-row">
          <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} disabled={syncing}
            className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm outline-none focus:border-brand-500 dark:border-gray-600 dark:bg-gray-900 dark:text-white"
            aria-label={english ? "Source URL" : "岗位源链接"} />
          <button onClick={sync} disabled={syncing || !sourceUrl.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50">
            {syncing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
            {syncing ? (english ? "Reading..." : "读取中……") : (english ? "Sync now" : "立即同步")}
          </button>
          <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700" title={english ? "Optional CSV/XLSX fallback" : "可选的 CSV/XLSX 备用导入"}>
            <Upload className="h-4 w-4" />{english ? "File fallback" : "文件备用"}
            <input type="file" accept=".csv,.xlsx" className="hidden" disabled={syncing} onChange={(event) => { void importFallback(event.target.files?.[0]); event.target.value = ""; }} />
          </label>
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-xs"><button type="button" onClick={() => setSourceUrl(DEFAULT_SOURCE)} className="rounded-full bg-blue-50 px-2.5 py-1 text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">腾讯岗位源</button><button type="button" onClick={() => setSourceUrl(FEISHU_SOURCE)} className="rounded-full bg-sky-50 px-2.5 py-1 text-sky-700 dark:bg-sky-950/30 dark:text-sky-300">飞书岗位源</button><span className="self-center text-gray-400">已配置 {stats.schedule.source_urls?.length || 2} 个来源，自动同步后合并去重</span></div>
        {message && <div className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">{message}</div>}
      </div>

      <details className="group rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3"><span className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100"><Settings2 className="h-4 w-4 text-brand-600" />我的求职偏好</span><span className="text-xs text-gray-500 group-open:hidden">点击填写，保存后立即重新评分</span><span className="hidden text-xs text-gray-500 group-open:inline">收起</span></summary>
        <div className="border-t border-gray-100 px-4 py-4 dark:border-gray-700">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {[
              ["target_roles", "目标岗位", "如：算法工程师，AI 产品经理"],
              ["preferred_locations", "优先城市", "如：北京，上海"],
              ["acceptable_locations", "可接受城市", "如：杭州，深圳"],
              ["industries", "目标行业", "如：人工智能，芯片/IC"],
              ["preferred_keywords", "期望关键词", "如：大模型，计算机视觉"],
              ["excluded_keywords", "排除关键词", "如：销售，外包"],
              ["company_blacklist", "排除公司", "用逗号分隔"],
              ["excluded_locations", "排除地点", "用逗号分隔"],
            ].map(([field, label, placeholder]) => <label key={field} className="text-xs text-gray-600 dark:text-gray-300"><span className="mb-1 block font-medium">{label}</span><input value={(preferences[field as keyof JobPreferences] as string[]).join("，")} onChange={(event) => updatePreferenceList(field as keyof JobPreferences, event.target.value)} placeholder={placeholder} className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm outline-none focus:border-brand-500 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label>)}
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div><div className="mb-2 text-xs font-medium text-gray-600 dark:text-gray-300">招聘类型</div><div className="flex flex-wrap gap-2">{["秋招", "实习", "提前批", "正式批", "夏令营"].map((value) => <button type="button" key={value} onClick={() => togglePreference("recruitment_types", value)} className={`rounded-full border px-3 py-1.5 text-xs ${preferences.recruitment_types.includes(value) ? "border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300" : "border-gray-200 text-gray-600 dark:border-gray-600 dark:text-gray-300"}`}>{value}</button>)}</div></div>
            <div><div className="mb-2 text-xs font-medium text-gray-600 dark:text-gray-300">公司类型</div><div className="flex flex-wrap gap-2">{["国企/央企", "外企", "科研/事业单位", "上市公司", "其他企业"].map((value) => <button type="button" key={value} onClick={() => togglePreference("company_types", value)} className={`rounded-full border px-3 py-1.5 text-xs ${preferences.company_types.includes(value) ? "border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300" : "border-gray-200 text-gray-600 dark:border-gray-600 dark:text-gray-300"}`}>{value}</button>)}</div></div>
          </div>
          <details className="mt-4 rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-900/60"><summary className="cursor-pointer text-xs font-medium text-gray-600 dark:text-gray-300">高级：评分权重</summary><div className="mt-3 grid gap-3 md:grid-cols-2">{Object.entries({ skills: "技能", role: "岗位", location: "地点", industry: "行业", company: "公司类型", recruitment: "招聘类型", referral: "内推" }).map(([key, label]) => <label key={key} className="flex items-center gap-3 text-xs text-gray-600 dark:text-gray-300"><span className="w-16">{label}</span><input className="min-w-0 flex-1" type="range" min="0" max="50" step="5" value={preferences.weights[key] ?? 0} onChange={(event) => setPreferences((current) => ({ ...current, weights: { ...current.weights, [key]: Number(event.target.value) } }))} /><span className="w-6 text-right">{preferences.weights[key] ?? 0}</span></label>)}</div><p className="mt-2 text-[11px] text-gray-400">权重会自动按比例换算为 100 分，无需手动保证总和为 100。</p></details>
          <div className="mt-4 flex justify-end"><button onClick={savePreferences} disabled={savingPreferences} className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">{savingPreferences ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}保存偏好并重新评分</button></div>
        </div>
      </details>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {[
          [english ? "Jobs" : "当前场景岗位", stats.by_scene[scene] || 0, BriefcaseBusiness],
          [english ? "Companies" : "公司数量", stats.companies, Building2],
          [english ? "Strong matches" : "高匹配岗位", highMatches, Target],
          [english ? "Last sync" : "最后同步", stats.last_sync ? fmtTime(stats.last_sync.created_at) : (english ? "Never" : "尚未"), Clock3],
        ].map(([label, value, Icon]: any) => <div key={label} className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2.5 shadow-sm dark:border-gray-700 dark:bg-gray-800"><Icon className="h-5 w-5 shrink-0 text-brand-600" /><div className="min-w-0"><div className="truncate text-lg font-bold leading-5 text-gray-900 dark:text-white">{value}</div><div className="text-[11px] text-gray-500">{label}</div></div></div>)}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={english ? "Search company, role, location or skill" : "搜索公司、岗位、地点或技能"} className="w-full rounded-lg border border-gray-200 py-2.5 pl-9 pr-3 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></div>
          <div className="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-300"><Filter className="h-4 w-4" /><span>{english ? "Minimum" : "最低匹配"} {minScore}</span><input type="range" min="0" max="90" step="10" value={minScore} onChange={(event) => setMinScore(Number(event.target.value))} /></div>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <select value={companyType} onChange={(event) => setCompanyType(event.target.value)} className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-white">
            <option value="">全部公司类型</option><option>国企/央企</option><option>外企</option><option>科研/事业单位</option><option>上市公司</option><option>其他企业</option>
          </select>
          <select value={matchLevel} onChange={(event) => setMatchLevel(event.target.value)} className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-white">
            <option value="">全部匹配度</option><option>高匹配</option><option>中匹配</option><option>低匹配</option>
          </select>
          <select value={recruitmentType} onChange={(event) => setRecruitmentType(event.target.value)} className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-white">
            <option value="">全部招聘类型</option><option>秋招</option><option>实习</option><option>提前批</option><option>正式批</option><option>夏令营</option>
          </select>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
          {profile.preferred_roles.slice(0, 5).map((item) => <span key={item} className="rounded-full bg-brand-50 px-2.5 py-1 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300">{item}</span>)}
          {profile.preferred_locations.map((item) => <span key={item} className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-700">{item}</span>)}
        </div>
      </div>

      {!favoriteOnly && !loading && dailyItems.length > 0 && <section>
        <div className="mb-3 flex items-center gap-2"><Sparkles className="h-5 w-5 text-amber-500" /><h3 className="text-lg font-bold text-gray-900 dark:text-white">每日推荐</h3><span className="text-xs text-gray-500">未处理企业中匹配度最高的 3 家</span></div>
        <div className="grid gap-4 xl:grid-cols-3">{dailyItems.map((job) => renderJobCard(job, true))}</div>
      </section>}

      {favoriteOnly && !loading && <div className="flex items-center gap-2"><Heart className="h-5 w-5 fill-current text-rose-500" /><h3 className="text-lg font-bold text-gray-900 dark:text-white">收藏夹</h3></div>}
      {loading ? <div className="flex justify-center py-16"><LoaderCircle className="h-8 w-8 animate-spin text-brand-600" /></div> : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gray-300 py-16 text-center dark:border-gray-700"><Radar className="mx-auto h-10 w-10 text-gray-300" /><p className="mt-3 text-gray-500">{favoriteOnly ? "收藏夹暂时为空" : scene === "civil_service" ? "考公考编信息源尚未接入，入口已预留。" : (english ? "Sync a source to see recommendations." : "同步岗位源后，这里会显示推荐结果。")}</p></div>
      ) : <div className="grid gap-4 xl:grid-cols-2">{items.map((job) => renderJobCard(job))}</div>}

      {trackingJob && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="确认求职记录">
        <form onSubmit={(event) => { event.preventDefault(); void confirmTrack(); }} className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl dark:bg-gray-800">
          <div className="flex items-start justify-between gap-4"><div><h3 className="text-lg font-bold text-gray-900 dark:text-white">确认加入求职记录</h3><p className="mt-1 text-xs text-gray-500">招聘信息可能已经变化，请确认岗位和 Base 地后再保存。</p></div><button type="button" onClick={() => setTrackingJob(null)} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700" aria-label="关闭"><X className="h-5 w-5" /></button></div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="text-sm text-gray-600 dark:text-gray-300"><span className="mb-1 block font-medium">企业名称</span><input required value={trackDraft.company} onChange={(event) => setTrackDraft((current) => ({ ...current, company: event.target.value }))} className="w-full rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label>
            <label className="text-sm text-gray-600 dark:text-gray-300"><span className="mb-1 block font-medium">岗位名称</span><input required value={trackDraft.role} onChange={(event) => setTrackDraft((current) => ({ ...current, role: event.target.value }))} className="w-full rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label>
            <label className="text-sm text-gray-600 dark:text-gray-300"><span className="mb-1 block font-medium">Base 地</span><input value={trackDraft.base} onChange={(event) => setTrackDraft((current) => ({ ...current, base: event.target.value }))} placeholder="如：北京、上海、深圳" className="w-full rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label>
            <label className="text-sm text-gray-600 dark:text-gray-300"><span className="mb-1 block font-medium">招聘类型</span><input value={trackDraft.recruitment_type} onChange={(event) => setTrackDraft((current) => ({ ...current, recruitment_type: event.target.value }))} placeholder="如：秋招、实习、提前批" className="w-full rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label>
            <label className="text-sm text-gray-600 dark:text-gray-300 sm:col-span-2"><span className="mb-1 block font-medium">岗位链接</span><input value={trackDraft.link} onChange={(event) => setTrackDraft((current) => ({ ...current, link: event.target.value }))} className="w-full rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label>
            <label className="text-sm text-gray-600 dark:text-gray-300 sm:col-span-2"><span className="mb-1 block font-medium">备注</span><textarea rows={5} value={trackDraft.notes} onChange={(event) => setTrackDraft((current) => ({ ...current, notes: event.target.value }))} className="w-full resize-y rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-600 dark:bg-gray-900 dark:text-white" /></label>
          </div>
          <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={() => setTrackingJob(null)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 dark:border-gray-600 dark:text-gray-300">取消</button><button type="submit" disabled={savingTrack || !trackDraft.company.trim() || !trackDraft.role.trim()} className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">{savingTrack && <LoaderCircle className="h-4 w-4 animate-spin" />}确认加入</button></div>
        </form>
      </div>}
    </div>
  );
}
