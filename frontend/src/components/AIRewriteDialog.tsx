import { useState, useEffect } from "react";
import { X, Loader2, Sparkles, Check, ArrowRight, RotateCcw } from "lucide-react";
import {
  rewriteText,
  getRewriteModes,
  type RewriteMode,
  type RewriteModeInfo,
} from "../api/client";
import type { Strings } from "../i18n";
import ErrorBoundary from "./ErrorBoundary";

interface AIRewriteDialogProps {
  isOpen: boolean;
  selectedText: string;
  surroundingContext: string;
  targetLanguage: "zh" | "en";
  apiKey: string;
  modelType: string;
  baseUrl: string;
  llmProtocol: string;
  t: Strings;
  onApply: (rewritten: string) => void;
  onClose: () => void;
}

export default function AIRewriteDialog({
  isOpen,
  selectedText,
  surroundingContext,
  targetLanguage,
  apiKey,
  modelType,
  baseUrl,
  llmProtocol,
  t,
  onApply,
  onClose,
}: AIRewriteDialogProps) {
  const [modes, setModes] = useState<RewriteModeInfo[]>([]);
  const [selectedMode, setSelectedMode] = useState<RewriteMode>("more_quantified");
  const [rewritten, setRewritten] = useState<string>("");
  const [isRewriting, setIsRewriting] = useState(false);
  const [error, setError] = useState<string>("");

  // Fallback strings (used when i18n snapshot doesn't have the rewrite field)
  const trFallback = {
    title: "AI Rewrite",
    original: "Original",
    mode: "Mode",
    rewritten: "Rewritten",
    rewriteBtn: "Rewrite",
    rewriting: "Rewriting...",
    placeholder: "Click Rewrite",
    apply: "Apply",
    cancel: "Cancel",
    retry: "Retry",
    error: "Error",
    noSelection: "Select text first",
  } as const;

  // Defensive: cast through unknown to handle stale i18n snapshots
  // (e.g. browser hasn't reloaded with the latest i18n/index.ts).
  const tr: typeof trFallback =
    ((t as unknown as { rewrite?: typeof trFallback }).rewrite) || trFallback;

  // Load modes on first open
  useEffect(() => {
    if (isOpen && modes.length === 0) {
      getRewriteModes()
        .then((data) => {
          // Defensive: ensure modes is an array
          const list = Array.isArray(data?.modes) ? data.modes : [];
          setModes(list);
          if (list.length === 0) {
            setError("No rewrite modes available — check backend connection");
          }
        })
        .catch((e) => {
          const msg = e?.response?.data?.detail || e?.message || String(e);
          setError(msg);
        });
    }
  }, [isOpen, modes.length]);

  // Reset state whenever dialog opens
  useEffect(() => {
    if (isOpen) {
      setRewritten("");
      setError("");
      setIsRewriting(false);
    }
  }, [isOpen]);

  const handleRewrite = async () => {
    if (!selectedText.trim()) return;
    setIsRewriting(true);
    setError("");
    setRewritten("");
    try {
      const result = await rewriteText({
        text: selectedText,
        mode: selectedMode,
        context: surroundingContext,
        target_language: targetLanguage,
        api_key: apiKey || undefined,
        model_type: modelType || undefined,
        base_url: baseUrl || undefined,
        llm_protocol: llmProtocol || undefined,
      });
      if (result.status === "success") {
        setRewritten(result.rewritten);
      } else {
        setError(result.message || tr.error);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || tr.error);
    } finally {
      setIsRewriting(false);
    }
  };

  const handleApply = () => {
    if (rewritten) onApply(rewritten);
  };

  const handleRetry = () => {
    setRewritten("");
    setError("");
    void handleRewrite();
  };

  if (!isOpen) return null;

  // Helper: pick the right label / description language
  const modeLabel = (m: RewriteModeInfo) =>
    targetLanguage === "en" ? m.label_en : m.label_zh;
  const modeDesc = (m: RewriteModeInfo) =>
    targetLanguage === "en" ? m.desc_en : m.desc_zh;

  return (
    <ErrorBoundary
      fallback={(err, reset) => (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-gray-800">
            <h2 className="mb-2 text-lg font-semibold text-red-600">
              AI Rewrite error
            </h2>
            <p className="mb-4 text-sm text-gray-700 dark:text-gray-300">
              {err.message}
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
              >
                Close
              </button>
              <button
                type="button"
                onClick={reset}
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      )}
    >
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-2xl dark:bg-gray-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4 dark:border-gray-700 dark:bg-gray-800">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-brand-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              {tr.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 p-6">
          {/* Original text (read-only) */}
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {tr.original}
            </label>
            <div className="max-h-32 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 dark:border-gray-600 dark:bg-gray-700/40 dark:text-gray-200">
              {selectedText || <span className="italic text-gray-400">—</span>}
            </div>
          </div>

          {/* Mode selector */}
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {tr.mode}
            </label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {modes.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setSelectedMode(m.id)}
                  className={`flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors ${
                    selectedMode === m.id
                      ? "border-brand-500 bg-brand-50 dark:bg-brand-900/30"
                      : "border-gray-200 bg-white hover:border-brand-300 hover:bg-brand-50/50 dark:border-gray-600 dark:bg-gray-700/30 dark:hover:bg-brand-900/20"
                  }`}
                >
                  <span className="flex items-center gap-1 text-sm font-medium text-gray-900 dark:text-white">
                    <span>{m.icon}</span>
                    <span>{modeLabel(m)}</span>
                  </span>
                  <span className="text-xs leading-snug text-gray-500 dark:text-gray-400">
                    {modeDesc(m)}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Rewrite / Result area */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {tr.rewritten}
              </label>
              <div className="flex items-center gap-2">
                {!rewritten && !isRewriting && (
                  <button
                    type="button"
                    onClick={handleRewrite}
                    disabled={!selectedText.trim()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {tr.rewriteBtn}
                  </button>
                )}
                {rewritten && !isRewriting && (
                  <button
                    type="button"
                    onClick={handleRetry}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    {tr.retry}
                  </button>
                )}
              </div>
            </div>
            <div className="min-h-[120px] rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-600 dark:bg-gray-700/40">
              {isRewriting ? (
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {tr.rewriting}
                </div>
              ) : rewritten ? (
                <div className="space-y-2">
                  <div className="flex items-start gap-2 text-sm leading-relaxed text-gray-900 dark:text-white">
                    <ArrowRight className="mt-1 h-4 w-4 flex-shrink-0 text-brand-500" />
                    <p className="whitespace-pre-wrap">{rewritten}</p>
                  </div>
                </div>
              ) : (
                <p className="text-sm italic text-gray-400">{tr.placeholder}</p>
              )}
            </div>
            {error && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                ❌ {error}
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 flex items-center justify-end gap-2 border-t border-gray-200 bg-gray-50 px-6 py-4 dark:border-gray-700 dark:bg-gray-900/40">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
          >
            {tr.cancel}
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={!rewritten || isRewriting}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
            {tr.apply}
          </button>
        </div>
      </div>
    </div>
    </ErrorBoundary>
  );
}
