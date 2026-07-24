import { useState, useRef, useEffect } from "react";
import { Bot, Send, Play, Square, Loader2, User, Download, Mic, MicOff, Volume2, RotateCcw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { Strings } from "../i18n";
import { useSessionState } from "../hooks/useSessionState";
import { startMockInterview, submitMockAnswer, endMockInterview, getMockInterviewDownloadUrl, getMockInterviewTTSVoices, getResumeContent, getSettings, synthesizeMockInterviewSpeech, streamMockInterviewSpeech } from "../api/client";

interface Message {
  role: "user" | "assistant";
  content: string;
}

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: any) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: any) => void) | null;
};

const MINIMAX_VOICE_OPTIONS = [
  { id: "Chinese (Mandarin)_Reliable_Executive", label: "沉稳高管", gender: "male" },
  { id: "male-qn-jingying", label: "精英青年", gender: "male" },
  { id: "female-chengshu", label: "成熟女性", gender: "female" },
  { id: "Chinese (Mandarin)_Wise_Women", label: "阅历姐姐", gender: "female" },
];

const TTS_PROVIDER_OPTIONS = [
  {
    id: "minimax",
    label: "MiniMax API（推荐）",
    description: "推荐：需要 MiniMax 接口，响应快，语音质量不错。",
  },
  {
    id: "kokoro",
    label: "Kokoro 本地（均衡）",
    description: "本地生成：比 MiniMax 稍慢，质量略低，但实时体验可接受。",
  },
  {
    id: "chattts",
    label: "ChatTTS 本地（高质量）",
    description: "高质量：音质更好，但生成较慢；无 GPU 时会明显影响实时对话。",
  },
] as const;

type TTSProvider = (typeof TTS_PROVIDER_OPTIONS)[number]["id"];

export default function MockInterview({ t }: { t: Strings }) {
  const mi = t.mockInterview;
  const chatEndRef = useRef<HTMLDivElement>(null);
  const typingTimerRef = useRef<number | null>(null);
  const typingFullContentRef = useRef("");
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const voiceOutputEnabledRef = useRef(false);
  const lastAssistantTextRef = useRef("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef("");
  const audioCacheRef = useRef<Map<string, Blob>>(new Map());
  const ttsAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const [companyName, setCompanyName] = useSessionState("buping_mock_company", "MiniMax");
  const [companyIndustry, setCompanyIndustry] = useSessionState("buping_mock_industry", "AI");
  const [jobTitle, setJobTitle] = useSessionState("buping_mock_job_title", "Python 后端工程师");
  const [interviewType, setInterviewType] = useSessionState("buping_mock_type", "技术面试");
  const [interviewStyle, setInterviewStyle] = useSessionState("buping_mock_style", "专业型");
  const [resumeText, setResumeText] = useSessionState("buping_mock_resume", "");
  const [jobDesc, setJobDesc] = useSessionState("buping_mock_job_desc", "");
  const [resumeLoadedFromFile, setResumeLoadedFromFile] = useSessionState("buping_mock_resume_source", "");

  const [sessionId, setSessionId] = useSessionState<string | null>("buping_mock_session_id", null);
  const [history, setHistory] = useSessionState<Message[]>("buping_mock_history", []);
  const [userInput, setUserInput] = useSessionState("buping_mock_user_input", "");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useSessionState("buping_mock_status", "");
  const [evaluation, setEvaluation] = useSessionState("buping_mock_evaluation", "");
  const [reportPdfFile, setReportPdfFile] = useSessionState("buping_mock_report_pdf", "");
  const [animatedMessageIndex, setAnimatedMessageIndex] = useState<number | null>(null);
  const [animatedContent, setAnimatedContent] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [speechInputSupported, setSpeechInputSupported] = useState(false);
  const [speechOutputSupported, setSpeechOutputSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceOutputEnabled, setVoiceOutputEnabled] = useSessionState("buping_mock_voice_output", false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const [interviewMode, setInterviewMode] = useSessionState<"text" | "voice">("buping_mock_mode", "text");
  const [ttsProvider, setTtsProvider] = useSessionState<TTSProvider>("buping_mock_tts_provider", "minimax");
  const [minimaxVoice, setMinimaxVoice] = useSessionState("buping_mock_minimax_voice", "Chinese (Mandarin)_Reliable_Executive");
  const [kokoroVoice, setKokoroVoice] = useSessionState("buping_mock_kokoro_voice", "zf_001");
  const [kokoroVoiceOptions, setKokoroVoiceOptions] = useState<Array<{ id: string; label: string }>>([
    { id: "zf_001", label: "女声 zf_001" },
  ]);
  const [ttsSpeed, setTtsSpeed] = useSessionState("buping_mock_tts_speed", 1);

  useEffect(() => {
    mountedRef.current = true;
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, animatedContent]);

  useEffect(() => {
    setSpeechInputSupported(Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition));
    setSpeechOutputSupported(true);
    const loadSavedResume = async () => {
      try {
        let language = "zh";
        try {
          const settings = await getSettings();
          language = settings.resume_language || "zh";
        } catch {
          language = "zh";
        }
        const result = await getResumeContent(language);
        if (result.content?.trim() && !resumeText.trim()) {
          setResumeText(result.content);
          setResumeLoadedFromFile(language === "en" ? "data_folder/plain_text_resume.yaml" : "data_folder/plain_text_resume_zh.yaml");
        }
      } catch {
        setResumeLoadedFromFile("");
      }
    };
    void loadSavedResume();
    void getMockInterviewTTSVoices()
      .then((result) => {
        if (result.kokoro?.length) {
          setKokoroVoiceOptions(result.kokoro);
          setKokoroVoice((current) => result.kokoro.some((voice) => voice.id === current) ? current : result.kokoro[0].id);
        }
      })
      .catch(() => undefined);
    return () => {
      mountedRef.current = false;
      if (typingTimerRef.current !== null) {
        window.clearInterval(typingTimerRef.current);
      }
      recognitionRef.current?.abort();
      ttsAbortRef.current?.abort();
      audioRef.current?.pause();
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
      }
      window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    voiceOutputEnabledRef.current = voiceOutputEnabled;
    if (!voiceOutputEnabled) {
      window.speechSynthesis?.cancel();
      setVoiceStatus("");
    }
  }, [voiceOutputEnabled]);

  const clearTypingTimer = () => {
    if (typingTimerRef.current !== null) {
      window.clearInterval(typingTimerRef.current);
      typingTimerRef.current = null;
    }
  };

  const stopSpeaking = () => {
    ttsAbortRef.current?.abort();
    ttsAbortRef.current = null;
    audioRef.current?.pause();
    audioRef.current = null;
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = "";
    }
    window.speechSynthesis?.cancel();
    setVoiceStatus("");
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setIsListening(false);
  };

  const selectedVoiceGender = () => {
    if (ttsProvider === "minimax") {
      return MINIMAX_VOICE_OPTIONS.find((voice) => voice.id === minimaxVoice)?.gender || "female";
    }
    if (ttsProvider === "kokoro") {
      return kokoroVoice.startsWith("zm_") ? "male" : "female";
    }
    return "female";
  };

  const speakWithBrowserFallback = (text: string) => {
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.rate = ttsSpeed;
    utterance.pitch = 1;
    const browserVoices = window.speechSynthesis.getVoices().filter((voice) => voice.lang.toLowerCase().startsWith("zh"));
    const preferMale = selectedVoiceGender() === "male";
    const preferredNames = preferMale ? ["Yunxi", "Yunjian", "Kangkang"] : ["Xiaoxiao", "Xiaoyi", "Huihui"];
    utterance.voice = browserVoices.find((voice) => preferredNames.some((name) => voice.name.includes(name))) || browserVoices[0] || null;
    utterance.onstart = () => setVoiceStatus(`主语音不可用，正在使用浏览器${preferMale ? "男声" : "女声"}播报`);
    utterance.onend = () => setVoiceStatus("");
    utterance.onerror = () => setVoiceStatus("语音播报失败");
    window.speechSynthesis.speak(utterance);
  };

  const playAudioBlob = async (audioBlob: Blob) => {
    const audioUrl = URL.createObjectURL(audioBlob);
    audioUrlRef.current = audioUrl;
    const audio = new Audio(audioUrl);
    audioRef.current = audio;
    audio.onplaying = () => setVoiceStatus("正在朗读面试官问题");
    audio.onended = () => stopSpeaking();
    audio.onerror = () => {
      stopSpeaking();
      setVoiceStatus("音频播放失败");
    };
    await audio.play();
  };

  const playAudioStream = async (response: Response, cleanText: string, signal: AbortSignal) => {
    if (!("MediaSource" in window) || !MediaSource.isTypeSupported("audio/mpeg")) {
      throw new Error("当前浏览器不支持流式 MP3 播放");
    }
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("TTS stream returned empty body");
    }

    const mediaSource = new MediaSource();
    const audioUrl = URL.createObjectURL(mediaSource);
    audioUrlRef.current = audioUrl;
    const audio = new Audio(audioUrl);
    audioRef.current = audio;
    audio.onplaying = () => setVoiceStatus("正在流式朗读面试官问题");
    audio.onended = () => stopSpeaking();
    audio.onerror = () => {
      stopSpeaking();
      setVoiceStatus("流式音频播放失败");
    };

    const chunks: ArrayBuffer[] = [];
    let sourceBuffer: SourceBuffer;
    await new Promise<void>((resolve, reject) => {
      mediaSource.addEventListener("sourceopen", () => {
        try {
          sourceBuffer = mediaSource.addSourceBuffer("audio/mpeg");
          resolve();
        } catch (error) {
          reject(error);
        }
      }, { once: true });
      mediaSource.addEventListener("error", () => reject(new Error("MediaSource 初始化失败")), { once: true });
    });

    const appendChunk = (chunk: ArrayBuffer) =>
      new Promise<void>((resolve, reject) => {
        const onUpdateEnd = () => {
          sourceBuffer.removeEventListener("updateend", onUpdateEnd);
          sourceBuffer.removeEventListener("error", onError);
          resolve();
        };
        const onError = () => {
          sourceBuffer.removeEventListener("updateend", onUpdateEnd);
          sourceBuffer.removeEventListener("error", onError);
          reject(new Error("流式音频缓冲失败"));
        };
        sourceBuffer.addEventListener("updateend", onUpdateEnd);
        sourceBuffer.addEventListener("error", onError);
        sourceBuffer.appendBuffer(chunk);
      });

    const playPromise = audio.play();
    let started = false;
    while (true) {
      if (signal.aborted) {
        await reader.cancel();
        return;
      }
      const { done, value } = await reader.read();
      if (done) break;
      if (!value?.length) continue;
      const chunk = value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer;
      chunks.push(chunk);
      await appendChunk(chunk);
      if (!started) {
        started = true;
        setVoiceStatus("正在接收并播放 MiniMax 语音");
      }
    }
    if (mediaSource.readyState === "open") {
      mediaSource.endOfStream();
    }
    await playPromise;

    const audioBlob = new Blob(chunks, { type: "audio/mpeg" });
    audioCacheRef.current.set(cleanText, audioBlob);
    if (audioCacheRef.current.size > 24) {
      const oldestKey = audioCacheRef.current.keys().next().value;
      if (oldestKey) audioCacheRef.current.delete(oldestKey);
    }
  };

  const speakText = async (text: string) => {
    if (!voiceOutputEnabledRef.current) {
      return;
    }
    const cleanText = text.replace(/[#*_`>-]/g, "").trim();
    if (!cleanText) return;
    const rate = `${Math.round((ttsSpeed - 1) * 100)}%`;
    const providerVoice = ttsProvider === "minimax" ? minimaxVoice : ttsProvider === "kokoro" ? kokoroVoice : "";
    const audioCacheKey = `${ttsProvider}|${providerVoice}|${ttsSpeed.toFixed(2)}|${cleanText}`;

    stopSpeaking();
    const cachedAudio = audioCacheRef.current.get(audioCacheKey);
    if (cachedAudio) {
      setVoiceStatus("正在播放缓存语音");
      try {
        await playAudioBlob(cachedAudio);
      } catch {
        speakWithBrowserFallback(cleanText);
      }
      return;
    }

    const controller = new AbortController();
    ttsAbortRef.current = controller;
    setVoiceStatus(ttsProvider === "minimax" ? "正在连接 MiniMax 流式语音" : "正在生成本地语音");

    try {
      if (ttsProvider === "minimax") {
        try {
          const streamResponse = await streamMockInterviewSpeech(
            { text: cleanText, provider: "minimax", voice: providerVoice, rate },
            controller.signal,
          );
          if (controller.signal.aborted) return;
          await playAudioStream(streamResponse, audioCacheKey, controller.signal);
          return;
        } catch {
          if (controller.signal.aborted) return;
          setVoiceStatus("流式语音不可用，正在尝试普通语音");
        }
      }

      const audioBlob = await synthesizeMockInterviewSpeech(
        { text: cleanText, provider: ttsProvider, voice: providerVoice, rate },
        controller.signal,
      );
      if (controller.signal.aborted) return;

      audioCacheRef.current.set(audioCacheKey, audioBlob);
      if (audioCacheRef.current.size > 24) {
        const oldestKey = audioCacheRef.current.keys().next().value;
        if (oldestKey) audioCacheRef.current.delete(oldestKey);
      }
      await playAudioBlob(audioBlob);
    } catch (err: any) {
        if (controller.signal.aborted) return;
      let detail = err?.response?.data?.detail || err?.message || "";
      if (err?.response?.data instanceof Blob) {
        try {
          const errorText = await err.response.data.text();
          detail = JSON.parse(errorText)?.detail || errorText || detail;
        } catch {
          detail = err?.message || "";
        }
      }
      setVoiceStatus(detail ? `高质量语音不可用，已切换浏览器播报：${detail}` : "高质量语音不可用，已切换浏览器播报");
      speakWithBrowserFallback(cleanText);
    }
  };

  const replayLatestAssistant = () => {
    const latest = [...history].reverse().find((msg) => msg.role === "assistant")?.content || lastAssistantTextRef.current;
    if (!latest) return;
    lastAssistantTextRef.current = latest;
    void speakText(latest);
  };

  const switchInterviewMode = (mode: "text" | "voice") => {
    setInterviewMode(mode);
    const enableVoice = mode === "voice";
    voiceOutputEnabledRef.current = enableVoice;
    setVoiceOutputEnabled(enableVoice);
    if (!enableVoice) {
      stopListening();
      stopSpeaking();
      return;
    }
    const latest = [...history].reverse().find((msg) => msg.role === "assistant")?.content || lastAssistantTextRef.current;
    if (latest) {
      void speakText(latest);
    }
  };

  const toggleListening = () => {
    if (!speechInputSupported) {
      setStatus("当前浏览器不支持语音输入，请使用 Chrome 或 Edge");
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }

    stopSpeaking();
    const SpeechRecognitionCtor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition: SpeechRecognitionLike = new SpeechRecognitionCtor();
    const seedText = userInput.trim();
    let finalText = seedText;

    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event: any) => {
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0]?.transcript || "";
        if (event.results[i].isFinal) {
          finalText = `${finalText}${finalText ? " " : ""}${transcript.trim()}`.trim();
        } else {
          interimText += transcript;
        }
      }
      setUserInput(`${finalText}${interimText ? ` ${interimText}` : ""}`.trim());
    };
    recognition.onerror = () => {
      setIsListening(false);
      setVoiceStatus("语音输入失败");
    };
    recognition.onend = () => {
      setIsListening(false);
      setVoiceStatus("");
    };

    recognitionRef.current = recognition;
    setIsListening(true);
    setVoiceStatus("正在听你说话");
    recognition.start();
  };

  const startTypewriter = (nextHistory: Message[]) => {
    clearTypingTimer();
    const assistantIndex = [...nextHistory].map((msg) => msg.role).lastIndexOf("assistant");
    if (assistantIndex < 0) {
      setHistory(nextHistory);
      return;
    }

    const fullContent = nextHistory[assistantIndex].content;
    lastAssistantTextRef.current = fullContent;
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
        void speakText(fullContent);
      }
    }, 18);
  };

  const skipTypewriter = () => {
    clearTypingTimer();
    setAnimatedContent(typingFullContentRef.current);
    setAnimatedMessageIndex(null);
    setIsTyping(false);
    void speakText(typingFullContentRef.current);
  };

  const handleStart = async (mode: "text" | "voice") => {
    stopListening();
    stopSpeaking();
    if (!resumeText.trim() || !jobDesc.trim()) {
      setStatus("❌ 请提供简历内容和职位描述");
      return;
    }
    setInterviewMode(mode);
    voiceOutputEnabledRef.current = mode === "voice";
    setVoiceOutputEnabled(mode === "voice");
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
      if (mountedRef.current) startTypewriter(result.history as Message[]);
      else setHistory(result.history as Message[]);
      setSessionId(result.session_id);
      setStatus(result.status);
      setEvaluation("");
      setReportPdfFile("");
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
    stopListening();
    stopSpeaking();
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
      if (mountedRef.current) startTypewriter(result.history as Message[]);
      else setHistory(result.history as Message[]);
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
    stopListening();
    stopSpeaking();
    setLoading(true);
    try {
      const result = await endMockInterview({
        session_id: sessionId,
        history: history,
      });
      setEvaluation(result.evaluation);
      setReportPdfFile(result.pdf_filename || "");
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
                <textarea value={resumeText} onChange={(e) => { setResumeText(e.target.value); setResumeLoadedFromFile(""); }} placeholder={mi.resumeTextPlaceholder} rows={4} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-none" />
                {resumeLoadedFromFile && (
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">已自动加载：{resumeLoadedFromFile}</p>
                )}
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{mi.jobDesc}</label>
                <textarea value={jobDesc} onChange={(e) => setJobDesc(e.target.value)} placeholder={mi.jobDescPlaceholder} rows={3} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white resize-none" />
              </div>
            </div>

            {!sessionId ? (
              <div className="mt-4 grid grid-cols-1 gap-2">
                <button
                  onClick={() => handleStart("text")}
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-brand-700 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:from-brand-700 hover:to-brand-800 disabled:opacity-50"
                >
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  开始文字面试
                </button>
                <button
                  onClick={() => handleStart("voice")}
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-brand-500 bg-brand-50 px-4 py-2.5 text-sm font-semibold text-brand-700 transition-all hover:bg-brand-100 disabled:opacity-50 dark:bg-brand-900/30 dark:text-brand-300 dark:hover:bg-brand-900/50"
                  title="使用 MiniMax 流式语音，可在面试中调整音色和语速"
                >
                  <Volume2 className="h-4 w-4" />
                  开始语音面试
                </button>
                <p className="text-xs text-gray-500 dark:text-gray-400">推荐使用 MiniMax API：需要 MiniMax 接口，速度快，语音质量不错；也可切换本地 Kokoro 或高质量但较慢的 ChatTTS。</p>
              </div>
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
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-3 dark:border-gray-700">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">{mi.chat}</h3>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <div className="inline-flex overflow-hidden rounded-lg border border-gray-200 text-xs font-medium dark:border-gray-700">
                  <button
                    type="button"
                    onClick={() => switchInterviewMode("text")}
                    className={`px-3 py-1.5 ${
                      interviewMode === "text"
                        ? "bg-brand-600 text-white"
                        : "text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                    }`}
                  >
                    文字
                  </button>
                  <button
                    type="button"
                    onClick={() => switchInterviewMode("voice")}
                    title="使用 MiniMax 流式语音，可调整音色和语速"
                    className={`px-3 py-1.5 ${
                      interviewMode === "voice"
                        ? "bg-brand-600 text-white"
                        : "text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                    }`}
                  >
                    语音
                  </button>
                </div>
                {interviewMode === "voice" && (
                  <>
                    <select
                      value={ttsProvider}
                      onChange={(event) => {
                        stopSpeaking();
                        setTtsProvider(event.target.value as TTSProvider);
                      }}
                      title={TTS_PROVIDER_OPTIONS.find((option) => option.id === ttsProvider)?.description || "选择语音方案"}
                      className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 outline-none transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                      {TTS_PROVIDER_OPTIONS.map((option) => (
                        <option key={option.id} value={option.id}>{option.label}</option>
                      ))}
                    </select>
                    {ttsProvider === "minimax" && (
                    <select
                      value={minimaxVoice}
                      onChange={(event) => {
                        stopSpeaking();
                        setMinimaxVoice(event.target.value);
                      }}
                      title="选择语音音色"
                      className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 outline-none transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    >
                      {MINIMAX_VOICE_OPTIONS.map((option) => (
                        <option key={option.id} value={option.id}>{option.label}</option>
                      ))}
                    </select>
                    )}
                    {ttsProvider === "kokoro" && (
                      <select
                        value={kokoroVoice}
                        onChange={(event) => {
                          stopSpeaking();
                          setKokoroVoice(event.target.value);
                        }}
                        title="选择本地 Kokoro 音色"
                        className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs text-gray-700 outline-none transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                      >
                        {kokoroVoiceOptions.map((option) => (
                          <option key={option.id} value={option.id}>{option.label}</option>
                        ))}
                      </select>
                    )}
                    {ttsProvider === "chattts" && (
                      <span
                        title="当前 ChatTTS 接口不支持选择固定说话人"
                        className="flex h-8 items-center rounded-lg border border-gray-200 px-2 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400"
                      >
                        自动音色
                      </span>
                    )}
                    <label className="flex h-8 items-center gap-2 rounded-lg border border-gray-200 px-2 text-xs text-gray-600 dark:border-gray-700 dark:text-gray-300">
                      <span>语速</span>
                      <input
                        type="range"
                        min="0.8"
                        max="1.3"
                        step="0.02"
                        value={ttsSpeed}
                        onChange={(event) => {
                          stopSpeaking();
                          setTtsSpeed(Number(event.target.value));
                        }}
                        className="w-20 accent-brand-600"
                      />
                      <span className="w-8 tabular-nums">{ttsSpeed.toFixed(2)}</span>
                    </label>
                  </>
                )}
                <button
                  type="button"
                  onClick={replayLatestAssistant}
                  disabled={!speechOutputSupported || !history.some((msg) => msg.role === "assistant")}
                  title="重播最近一个问题"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-500 transition-colors hover:bg-gray-50 disabled:opacity-40 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700"
                >
                  <RotateCcw className="h-4 w-4" />
                </button>
              </div>
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
                  {interviewMode === "voice" && (
                    <button
                      type="button"
                      onClick={toggleListening}
                      disabled={loading || isTyping}
                      title={isListening ? "停止语音输入" : "开始语音输入"}
                      className={`inline-flex items-center justify-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                        isListening
                          ? "bg-red-600 text-white hover:bg-red-700"
                          : "border border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
                      }`}
                    >
                      {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                    </button>
                  )}
                  <button
                    onClick={handleSubmit}
                    disabled={loading || isTyping || !userInput.trim()}
                    className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                  >
                    <Send className="h-4 w-4" />
                    {mi.send}
                  </button>
                </div>
                {voiceStatus && (
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">{voiceStatus}</div>
                )}
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
                {reportPdfFile && (
                  <a
                    href={getMockInterviewDownloadUrl(reportPdfFile)}
                    download
                    className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
                  >
                    <Download className="h-4 w-4" />
                    保存 PDF
                  </a>
                )}
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
