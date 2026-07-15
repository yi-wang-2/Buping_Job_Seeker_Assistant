import { useEffect, useState, type ReactNode } from "react";
import { getCurrentUser } from "../api/client";

export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "signed-in" | "anonymous">("loading");

  useEffect(() => {
    getCurrentUser().then(() => setState("signed-in")).catch(() => setState("anonymous"));
  }, []);

  if (state === "loading") {
    return <div className="flex min-h-screen items-center justify-center bg-gray-50 text-gray-500">正在确认登录状态…</div>;
  }

  if (state === "anonymous") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-6">
        <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
          <img src="/logo.png" alt="Buping" className="mx-auto mb-4 h-14 w-14 rounded-2xl" />
          <h1 className="text-2xl font-bold text-gray-900">登录 Buping</h1>
          <p className="mt-3 text-sm leading-6 text-gray-600">登录后，你的设置、简历和历史记录会按账号独立保存。</p>
          <a href="/signin-with-chatgpt?return_to=/resume" className="mt-6 inline-flex rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700">
            使用 ChatGPT 登录
          </a>
        </div>
      </div>
    );
  }

  return children;
}
