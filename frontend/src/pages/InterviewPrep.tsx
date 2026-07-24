import { useState } from "react";
import { BookOpen, Download, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Strings } from "../i18n";
import { generateInterviewPrep, getInterviewPrepDownloadUrl } from "../api/client";
import { useSessionState } from "../hooks/useSessionState";

export default function InterviewPrep({ t }: { t: Strings }) {
  const ip = t.interviewPrep;
  const [jobDesc, setJobDesc] = useSessionState("buping_interview_prep_job_desc", "");
  const [interviewType, setInterviewType] = useSessionState("buping_interview_prep_type", "综合面试");
  const [questionCount, setQuestionCount] = useSessionState("buping_interview_prep_question_count", 10);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useSessionState("buping_interview_prep_status", "");
  const [report, setReport] = useSessionState("buping_interview_prep_report", "");
  const [downloads, setDownloads] = useSessionState("buping_interview_prep_downloads", { md: "", pdf: "" });

  const handleGenerate = async () => {
    if (!jobDesc.trim()) {
      setStatus("❌ 请提供职位描述");
      return;
    }
    setLoading(true);
    setStatus(ip.generating);
    setReport("");
    setDownloads({ md: "", pdf: "" });
    try {
      const result = await generateInterviewPrep({
        job_description: jobDesc,
        interview_type: interviewType,
        question_count: questionCount,
      });
      const nextDownloads = { md: result.md_filename, pdf: result.pdf_filename };
      const successStatus = "✅ 报告生成成功！";
      setReport(result.report);
      setDownloads(nextDownloads);
      setStatus(successStatus);
    } catch (err: any) {
      const errorStatus = `❌ ${err.response?.data?.detail || err.message}`;
      setStatus(errorStatus);
    } finally {
      setLoading(false);
    }
  };

  const interviewTypes = ["综合面试", "技术面试", "HR 面试", "行为面试", "项目深挖", "英文面试"];

  return (
    <div className="page-enter max-w-5xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">{ip.title}</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config */}
        <div className="lg:col-span-1 space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <BookOpen className="h-4 w-4 text-brand-500" />
              配置
            </h3>

            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{ip.interviewType}</label>
                <select
                  value={interviewType}
                  onChange={(e) => setInterviewType(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  {interviewTypes.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                  {ip.questionCount}: {questionCount}
                </label>
                <input
                  type="range"
                  min={3}
                  max={20}
                  value={questionCount}
                  onChange={(e) => setQuestionCount(Number(e.target.value))}
                  className="w-full accent-brand-600"
                />
                <div className="flex justify-between text-xs text-gray-400">
                  <span>3</span>
                  <span>20</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Main */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <label className="mb-2 block text-sm font-semibold text-gray-700 dark:text-gray-300">{ip.jobDesc}</label>
            <textarea
              value={jobDesc}
              onChange={(e) => setJobDesc(e.target.value)}
              placeholder={ip.jobDescPlaceholder}
              rows={8}
              className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-none"
            />
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:from-brand-700 hover:to-brand-800 hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BookOpen className="h-4 w-4" />}
            {loading ? ip.generating : ip.generate}
          </button>

          {status && (
            <div className={`rounded-xl border p-4 text-sm ${
              status.startsWith("✅")
                ? "border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300"
                : "border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
            }`}>
              {status}
            </div>
          )}

          {/* Report */}
          {report && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{ip.report}</h3>
                <div className="flex gap-2">
                  <a href={getInterviewPrepDownloadUrl(downloads.md)} download className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700">
                    <Download className="h-4 w-4" /> Markdown
                  </a>
                  <a href={getInterviewPrepDownloadUrl(downloads.pdf)} download className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-xs font-medium text-white hover:bg-brand-700">
                    <Download className="h-4 w-4" /> PDF
                  </a>
                </div>
              </div>
              <div className="markdown-body prose prose-sm max-w-none dark:prose-invert">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({ children }) => (
                      <div className="markdown-table-wrap"><table>{children}</table></div>
                    ),
                  }}
                >
                  {report}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
