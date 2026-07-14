import { useEffect, useState } from "react";
import { discoverModels } from "../api/client";

export function useAvailableModels(apiKey: string, baseUrl: string, protocol: string): string[] {
  const [models, setModels] = useState<string[]>([]);

  useEffect(() => {
    setModels([]);
    if (!apiKey.trim() || !baseUrl.trim()) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const result = await discoverModels({
          llm_api_key: apiKey,
          llm_base_url: baseUrl,
          llm_protocol: protocol,
        });
        if (!cancelled) setModels(Array.isArray(result.models) ? result.models : []);
      } catch {
        if (!cancelled) setModels([]);
      }
    }, 600);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [apiKey, baseUrl, protocol]);

  return models;
}
