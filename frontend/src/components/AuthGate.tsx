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
          <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-left text-xs leading-5 text-amber-950">
            <p className="font-semibold">数据与隐私说明</p>
            <p className="mt-1">
              你在本站提交的设置、简历和使用记录会上传并存储在 OpenAI Sites 提供的云端基础设施中，并按登录账号隔离。本站维护者不会主动查看、使用或向第三方出售你的内容；但无法承诺对云端数据绝对“不可访问”。OpenAI 对托管数据的处理适用其相关条款与隐私文件。
            </p>
            <p className="mt-2">
              你的模型 API 密钥仅保存在当前浏览器会话中，不写入本站云数据库。请勿提交支付卡、医疗健康信息或其他不必要的高度敏感数据。
            </p>
            <p className="mt-2">
              继续登录即表示你已阅读本说明。详情请参阅
              <a className="mx-1 font-medium underline" href="https://openai.com/policies/chatgpt-sites-terms/" target="_blank" rel="noreferrer">ChatGPT Sites 条款</a>
              和
              <a className="ml-1 font-medium underline" href="https://openai.com/policies/privacy-policy/" target="_blank" rel="noreferrer">OpenAI 隐私政策</a>。
            </p>
          </div>
          <a href="/signin-with-chatgpt?return_to=/resume" className="mt-6 inline-flex rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700">
            使用 ChatGPT 登录
          </a>
        </div>
      </div>
    );
  }

  return children;
}
