import { useState, useRef, useEffect } from "react";
import { Bot, Send, Play, Square, Loader2, User, Download } from "lucide-react";
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
  const typingTimerRef = useRef<number | null>(null);
  const typingFullContentRef = useRef("");

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
  const [animatedMessageIndex, setAnimatedMessageIndex] = useState<number | null>(null);
  const [animatedContent, setAnimatedContent] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, animatedContent]);

  useEffect(() => {
    return () => {
      if (typingTimerRef.current !== null) {
        window.clearInterval(typingTimerRef.current);
      }
    };
  }, []);

  const clearTypingTimer = () => {
    if (typingTimerRef.current !== null) {
      window.clearInterval(typingTimerRef.current);
      typingTimerRef.current = null;
    }
  };

  const startTypewriter = (nextHistory: Message[]) => {
    clearTypingTimer();
    const assistantIndex = [...nextHistory].map((msg) => msg.role).lastIndexOf("assistant");
    if (assistantIndex < 0) {
      setHistory(nextHistory);
      return;
    }

    const fullContent = nextHistory[assistantIndex].content;
    typingFullContentRef.current = fullContent;
    setHistory(nextHistory);
    setAnimatedMessageIndex(assistantIndex);
    setAnimatedContent("");
    setIsTyping(true);

    let cursor = 0;
    typingTimerRef.current = window.setInterval(() => {
      cursor = Math.min(cursor + 2, fullContent.length);
      setAnimatedContent(fullContent.slice(0, cursor));
      if (cursor >= fullContent.length) {
        clearTypingTimer();
        setAnimatedMessageIndex(null);
        setAnimatedContent("");
        setIsTyping(false);
      }
    }, 18);
  };

  const skipTypewriter = () => {
    clearTypingTimer();
    setAnimatedContent(typingFullContentRef.current);
    setAnimatedMessageIndex(null);
    setIsTyping(false);
  };

  const escapeHtml = (value: string) =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const markdownToPrintHtml = (markdown: string) =>
    markdown
      .split(/\r?\n/)
      .map((rawLine) => {
        const line = rawLine.trim();
        if (!line) return "";
        const content = escapeHtml(line).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        if (line.startsWith("### ")) return `<h3>${content.slice(4)}</h3>`;
        if (line.startsWith("## ")) return `<h2>${content.slice(3)}</h2>`;
        if (line.startsWith("# ")) return `<h1>${content.slice(2)}</h1>`;
        if (line === "---") return "<hr />";
        return `<p>${content}</p>`;
      })
      .join("\n");

  const handleSavePdf = () => {
    const printWindow = window.open("", "_blank", "noopener,noreferrer,width=900,height=1200");
    if (!printWindow) {
      setStatus("无法打开打印窗口，请检查浏览器弹窗设置");
      return;
    }

    const conversationHtml = history
      .map((msg) => {
        const speaker = msg.role === "user" ? "候选人" : "面试官";
        return `<div class="message ${msg.role}">
          <div class="speaker">${speaker}</div>
          <p>${escapeHtml(msg.content)}</p>
        </div>`;
      })
      .join("\n");

    printWindow.document.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>模拟面试评估报告</title>
  <style>
    @page { size: A4; margin: 16mm; }
    body {
      color: #111827;
      font-family: "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
      font-size: 12px;
      line-height: 1.55;
    }
    h1 { font-size: 22px; margin: 0 0 14px; }
    h2 { font-size: 16px; margin: 22px 0 10px; border-bottom: 1px solid #e5e7eb; padding-bottom: 5px; }
    h3 { font-size: 14px; margin: 16px 0 8px; }
    p { margin: 0 0 8px; white-space: pre-wrap; }
    hr { border: 0; border-top: 1px solid #e5e7eb; margin: 18px 0; }
    .meta { color: #6b7280; margin-bottom: 18px; }
    .message { break-inside: avoid; margin: 0 0 10px; padding: 10px 12px; border: 1px solid #e5e7eb; border-radius: 8px; }
    .speaker { font-weight: 700; margin-bottom: 4px; }
    .assistant { background: #f9fafb; }
  </style>
</head>
<body>
  <h1>模拟面试评估报告</h1>
  <div class="meta">生成时间：${new Date().toLocaleString()}</div>
  <h2>面试问答记录</h2>
  ${conversationHtml}
  <h2>面试评估</h2>
  ${markdownToPrintHtml(evaluation)}
  <script>
    window.addEventListener("load", () => {
      window.print();
    });
  </script>
</body>
</html>`);
    printWindow.document.close();
  };

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
      startTypewriter(result.history as Message[]);
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
    if (isTyping) {
      skipTypewriter();
      return;
    }
    if (!userInput.trim() || !sessionId) return;
    const msg = userInput;
    const previousHistory = history;
    setUserInput("");
    setHistory([...previousHistory, { role: "user", content: msg }]);
    setLoading(true);
    try {
      const result = await submitMockAnswer({
        session_id: sessionId,
        user_message: msg,
        history: previousHistory,
        context_window: 5,
      });
      startTypewriter(result.history as Message[]);
      setStatus(result.status);
    } catch (err: any) {
      setHistory(previousHistory);
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
                      <ReactMarkdown>{i === animatedMessageIndex ? animatedContent : msg.content}</ReactMarkdown>
                      {i === animatedMessageIndex && isTyping && (
                        <span className="ml-0.5 inline-block h-4 w-1 animate-pulse rounded bg-current align-text-bottom" />
                      )}
                    </div>
                    {i === animatedMessageIndex && isTyping && (
                      <button
                        type="button"
                        onClick={skipTypewriter}
                        className="mt-2 text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-brand-300 dark:hover:text-brand-200"
                      >
                        跳过
                      </button>
                    )}
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
                    disabled={loading || isTyping}
                    className="flex-1 rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                  />
                  <button
                    onClick={handleSubmit}
                    disabled={loading || isTyping || !userInput.trim()}
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
              <div className="mb-4 flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{mi.evaluation}</h3>
                <button
                  type="button"
                  onClick={handleSavePdf}
                  className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
                >
                  <Download className="h-4 w-4" />
                  保存 PDF
                </button>
              </div>
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
