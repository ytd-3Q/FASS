import React from "react";
import { api, getApiKey, setApiKey } from "../lib/api";
import { usePrompt } from "./PromptProvider";

export function ApiKeyBanner() {
  const [key, setKey] = React.useState(getApiKey());
  const [status, setStatus] = React.useState<string | null>(null);
  const [modelsSample, setModelsSample] = React.useState<string[] | null>(null);
  const { prompt } = usePrompt();

  return (
    <div className="flex items-center gap-2 text-xs text-slate-600">
      <button
        className="rounded-md border border-[#87CEEB]/40 bg-white/70 px-2 py-1 text-slate-900 hover:bg-white"
        onClick={async () => {
          const next = await prompt({
            title: "设置 FASS Gateway API Key",
            description: "留空表示清除。该 Key 会存储在浏览器 localStorage。",
            defaultValue: key ?? "",
            placeholder: "sk-... 或自定义 Key",
            kind: "password"
          });
          if (next === null) return;
          const v = next.trim() ? next.trim() : null;
          setApiKey(v);
          setKey(v);
          setModelsSample(null);
          setStatus("保存完成，Ping 测试中…");
          try {
            await api.get("/api/config/upstreams");
            const m = await api.get("/api/models/list");
            await api.get("/api/config/models");
            const ids = (m?.items || []).map((x: any) => x?.id).filter(Boolean).slice(0, 6);
            setModelsSample(ids);
            setStatus("Ping 成功");
          } catch (e: any) {
            setStatus(`Ping 失败：${String(e?.message || e)}`);
          } finally {
            window.setTimeout(() => setStatus(null), 3500);
          }
        }}
      >
        API Key
      </button>
      <button
        className="rounded-md border border-[#87CEEB]/40 bg-white/70 px-2 py-1 text-slate-900 hover:bg-white"
        onClick={async () => {
          try {
            await api.get("/api/models/list");
            setStatus("连接正常");
          } catch {
            setStatus("连接失败");
          } finally {
            window.setTimeout(() => setStatus(null), 1200);
          }
        }}
      >
        Ping
      </button>
      <span className="text-slate-500">{key ? "已设置" : "未设置"}</span>
      {status ? <span className="text-slate-900">{status}</span> : null}
      {modelsSample?.length ? <span className="text-slate-500">models: {modelsSample.join(", ")}</span> : null}
    </div>
  );
}
