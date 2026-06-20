import { useState, useRef, useEffect } from "react";
import { Bot, Send, Play, Square, Loader2, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { Strings } from "../i18n";
import { startMockInterview, submitMockAnswer, endMockInterview } from "../api/client";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function MockInterview({ t }: { t: Strings }) {
  const mi = t.mockInterview;
  const chatEndRef = useRef<HTMLDivElement>(null);

  const [companyName, setCompanyName] = useState("MiniMax");
  const [companyIndustry, setCompanyIndustry] = useState("AI");
  const [jobTitle, setJobTitle] = useState("Python 后端工程师");
  const [interviewType, setInterviewType] = useState("技术面试");
  const [interviewStyle, setInterviewStyle] = useState("专业型");
  const [resumeText, setResumeText] = useState("");
  const [jobDesc, setJobDesc] = useState("");

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [history, setHistory] = useState<Message[]>([]);
  const [userInput, setUserInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [evaluation, setEvaluation] = useState("");

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  const handleStart = async () => {
    if (!resumeText.trim() || !jobDesc.trim()) {
      setStatus("❌ 请提供简历内容和职位描述");
      return;
    }
    setLoading(true);
    try {
      const result = await startMockInterview({
        resume_text: resumeText,
        job_description: jobDesc,
        company_name: companyName,
        company_industry: companyIndustry,
        job_title: jobTitle,
        interview_type: interviewType,
        interview_style: interviewStyle,
      });
      setHistory(result.history as Message[]);
      setSessionId(result.session_id);
      setStatus(result.status);
      setEvaluation("");
    } catch (err: any) {
      setStatus(`❌ ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!userInput.trim() || !sessionId) return;
    const msg = userInput;
    setUserInput("");
    setLoading(true);
    try {
      const result = await submitMockAnswer({
        session_id: sessionId,
        user_message: msg,
        history: history,
      });
      setHistory(result.history as Message[]);
      setStatus(result.status);
    } catch (err: any) {
      setStatus(`❌ ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleEnd = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const result = await endMockInterview({
        session_id: sessionId,
        history: history,
      });
      setEvaluation(result.evaluation);
      setSessionId(null);
      setStatus("✅ 面试已结束");
    } catch (err: any) {
      setStatus(`❌ ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const interviewTypes = ["综合面试", "技术面试", "行为面试", "项目深挖", "系统设计"];
  const interviewStyles = ["友善型", "专业型", "压力型", "学术型", "闲聊型"];

  return (
    <div className="page-enter max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">{mi.title}</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">{mi.desc}</p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config Panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <Bot className="h-4 w-4 text-brand-500" />
              {mi.config}
            </h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.companyName}</label>
                <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.companyIndustry}</label>
                <input value={companyIndustry} onChange={(e) => setCompanyIndustry(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.jobTitle}</label>
                <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.interviewType}</label>
                <select value={interviewType} onChange={(e) => setInterviewType(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white">
                  {interviewTypes.map((type) => <option key={type} value={type}>{type}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.interviewStyle}</label>
                <select value={interviewStyle} onChange={(e) => setInterviewStyle(e.target.value)} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white">
                  {interviewStyles.map((style) => <option key={style} value={style}>{style}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.resumeText}</label>
                <textarea value={resumeText} onChange={(e) => setResumeText(e.target.value)} placeholder={mi.resumeTextPlaceholder} rows={4} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-none" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.jobDesc}</label>
                <textarea value={jobDesc} onChange={(e) => setJobDesc(e.target.value)} placeholder={mi.jobDescPlaceholder} rows={3} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-none" />
              </div>
            </div>

            {!sessionId ? (
              <button
                onClick={handleStart}
                disabled={loading}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-700 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:from-brand-700 hover:to-brand-800 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {mi.start}
              </button>
            ) : (
              <button
                onClick={handleEnd}
                disabled={loading}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg transition-all hover:bg-red-700 disabled:opacity-50"
              >
                <Square className="h-4 w-4" />
                {mi.end}
              </button>
            )}
          </div>
        </div>

        {/* Chat Panel */}
        <div className="lg:col-span-2 flex flex-col">
          <div className="rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800 flex flex-col" style={{ minHeight: "500px" }}>
            {/* Chat header */}
            <div className="border-b border-gray-200 px-5 py-3 dark:border-gray-700">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">{mi.chat}</h3>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4" style={{ maxHeight: "400px" }}>
              {history.length === 0 && (
                <div className="flex h-full items-center justify-center text-gray-400 dark:text-gray-500">
                  <div className="text-center">
                    <Bot className="mx-auto h-12 w-12 mb-3 opacity-50" />
                    <p className="text-sm">点击「{mi.start}」开始模拟面试</p>
                  </div>
                </div>
              )}
              {history.map((msg, i) => (
                <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "assistant" && (
                    <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-900/30">
                      <Bot className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                    </div>
                  )}
                  <div
                    className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm ${
                      msg.role === "user"
                        ? "bg-brand-600 text-white rounded-br-md"
                        : "bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-white rounded-bl-md"
                    }`}
                  >
                    <div className="markdown-body prose prose-sm max-w-none dark:prose-invert">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                  {msg.role === "user" && (
                    <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gray-200 dark:bg-gray-600">
                      <User className="h-4 w-4 text-gray-600 dark:text-gray-300" />
                    </div>
                  )}
                </div>
              ))}
              {loading && history.length > 0 && (
                <div className="flex gap-3 justify-start">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-900/30">
                    <Bot className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                  </div>
                  <div className="rounded-2xl rounded-bl-md bg-gray-100 px-4 py-3 dark:bg-gray-700">
                    <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            {sessionId && (
              <div className="border-t border-gray-200 p-4 dark:border-gray-700">
                <div className="flex gap-2">
                  <input
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={mi.inputPlaceholder}
                    disabled={loading}
                    className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                  />
                  <button
                    onClick={handleSubmit}
                    disabled={loading || !userInput.trim()}
                    className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                  >
                    <Send className="h-4 w-4" />
                    {mi.send}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Status */}
          {status && (
            <div className={`mt-3 rounded-lg border p-3 text-sm ${
              status.startsWith("✅")
                ? "border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300"
                : "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300"
            }`}>
              {status}
            </div>
          )}

          {/* Evaluation */}
          {evaluation && (
            <div className="mt-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
              <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">{mi.evaluation}</h3>
              <div className="markdown-body prose prose-sm max-w-none dark:prose-invert">
                <ReactMarkdown>{evaluation}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
