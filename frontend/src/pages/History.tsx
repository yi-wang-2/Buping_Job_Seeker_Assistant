import { useState, useEffect } from "react";
import { Clock, RefreshCw, Trash2, FileText, Download } from "lucide-react";
import type { Strings } from "../i18n";
import { getHistory, clearHistory, getDownloadUrl } from "../api/client";

interface FileInfo {
  name: string;
  path: string;
  size: number;
  modified: string;
}

export default function History({ t }: { t: Strings }) {
  const ht = t.history;
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const result = await getHistory();
      setFiles(result.files);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleClear = async () => {
    if (!window.confirm(ht.confirmClear)) return;
    try {
      await clearHistory();
      setFiles([]);
    } catch {
      // ignore
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  };

  return (
    <div className="page-enter max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{ht.title}</h2>
        <div className="flex gap-2">
          <button
            onClick={fetchHistory}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            {ht.refresh}
          </button>
          <button
            onClick={handleClear}
            disabled={files.length === 0}
            className="flex items-center gap-2 rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            {ht.clear}
          </button>
        </div>
      </div>

      {files.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-300 py-20 dark:border-gray-600">
          <Clock className="h-12 w-12 text-gray-400 mb-4" />
          <p className="text-gray-500 dark:text-gray-400">{ht.empty}</p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-500 dark:text-gray-400">{ht.found.replace("{}", String(files.length))}</p>
          {files.map((file) => (
            <div
              key={file.name}
              className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-colors hover:border-brand-300 dark:border-gray-700 dark:bg-gray-800 dark:hover:border-brand-600"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 dark:bg-brand-900/20">
                <FileText className="h-5 w-5 text-brand-600 dark:text-brand-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{file.name}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {formatSize(file.size)} · {file.modified}
                </p>
              </div>
              <a
                href={getDownloadUrl(file.name)}
                download
                className="flex items-center gap-1.5 rounded-lg bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 transition-colors hover:bg-brand-100 dark:bg-brand-900/20 dark:text-brand-300 dark:hover:bg-brand-900/30"
              >
                <Download className="h-3.5 w-3.5" />
                Download
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
