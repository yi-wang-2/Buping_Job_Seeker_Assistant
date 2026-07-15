const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });

async function userId(request) {
  const email = request.headers.get("oai-authenticated-user-email")?.trim().toLowerCase();
  if (!email) return null;
  const bytes = new TextEncoder().encode(email);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function ensureSchema(db) {
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS user_settings (
      user_id TEXT PRIMARY KEY,
      settings_json TEXT NOT NULL DEFAULT '{}',
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS user_resumes (
      user_id TEXT NOT NULL,
      language TEXT NOT NULL,
      content TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (user_id, language)
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS user_history (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      name TEXT NOT NULL,
      path TEXT NOT NULL DEFAULT '',
      size INTEGER NOT NULL DEFAULT 0,
      modified TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS user_history_owner_idx ON user_history(user_id, modified DESC)"),
  ]);
}

async function handleApi(request, env, url) {
  const owner = await userId(request);
  if (!owner) return json({ detail: "Sign in with ChatGPT to continue" }, 401);
  await ensureSchema(env.DB);

  if (url.pathname === "/api/me" && request.method === "GET") {
    return json({ authenticated: true, user_id: owner });
  }

  if (url.pathname === "/api/settings" && request.method === "GET") {
    const row = await env.DB.prepare("SELECT settings_json FROM user_settings WHERE user_id = ?")
      .bind(owner).first();
    const settings = row ? JSON.parse(row.settings_json) : {};
    return json({
      llm_api_key: "",
      llm_model_type: "anthropic",
      llm_model: "MiniMax-M3",
      llm_base_url: "https://api.minimaxi.com/anthropic",
      llm_protocol: "anthropic",
      resume_language: "zh",
      system_language: "zh",
      ...settings,
    });
  }

  if (url.pathname === "/api/settings" && request.method === "PUT") {
    const body = await request.json();
    delete body.llm_api_key;
    await env.DB.prepare(`INSERT INTO user_settings (user_id, settings_json, updated_at)
      VALUES (?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(user_id) DO UPDATE SET settings_json = excluded.settings_json, updated_at = CURRENT_TIMESTAMP`)
      .bind(owner, JSON.stringify(body)).run();
    return json({ status: "success", message: "设置已按当前用户保存" });
  }

  if (url.pathname === "/api/settings/resume-content" && request.method === "GET") {
    const language = url.searchParams.get("language") === "en" ? "en" : "zh";
    const row = await env.DB.prepare("SELECT content FROM user_resumes WHERE user_id = ? AND language = ?")
      .bind(owner, language).first();
    return json({ content: row?.content || "", language });
  }

  if (url.pathname === "/api/settings/resume-content" && request.method === "PUT") {
    const body = await request.json();
    const language = body.language === "en" ? "en" : "zh";
    await env.DB.prepare(`INSERT INTO user_resumes (user_id, language, content, updated_at)
      VALUES (?, ?, ?, CURRENT_TIMESTAMP)
      ON CONFLICT(user_id, language) DO UPDATE SET content = excluded.content, updated_at = CURRENT_TIMESTAMP`)
      .bind(owner, language, String(body.content || "")).run();
    return json({ status: "success", message: "简历已按当前用户保存", validation: null });
  }

  if (url.pathname === "/api/history" && request.method === "GET") {
    const result = await env.DB.prepare(`SELECT name, path, size, modified FROM user_history
      WHERE user_id = ? ORDER BY modified DESC LIMIT 100`).bind(owner).all();
    return json({ files: result.results || [], count: result.results?.length || 0 });
  }

  if (url.pathname === "/api/history" && request.method === "DELETE") {
    const result = await env.DB.prepare("DELETE FROM user_history WHERE user_id = ?").bind(owner).run();
    return json({ status: "success", message: "当前用户的历史记录已清空", cleared: result.meta?.changes || 0 });
  }

  return json({ detail: "This cloud endpoint has not been migrated yet" }, 501);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) return handleApi(request, env, url);

    const response = await env.ASSETS.fetch(request);
    if (response.status !== 404) return response;
    if (request.method === "GET") {
      return env.ASSETS.fetch(new Request(new URL("/index.html", url), request));
    }
    return response;
  },
};
