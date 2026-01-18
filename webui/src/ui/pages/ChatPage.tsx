import React from "react";
import { api, getApiKey } from "../lib/api";

type ChatMsg = { role: "user" | "assistant" | "system"; content: string };

export function ChatPage() {
  const [input, setInput] = React.useState("");
  const [msgs, setMsgs] = React.useState<ChatMsg[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [models, setModels] = React.useState<Array<{ id: string; source: "newapi" | "ollama"; legacy: boolean }>>([]);
  const [modelId, setModelId] = React.useState<string>("");
  const [status, setStatus] = React.useState<string | null>(null);

  const loadModels = React.useCallback(async () => {
    try {
      const [m, d] = await Promise.all([api.get("/api/models/list"), api.get("/api/config/models")]);
      const list = (m?.items || []) as any[];
      const ms = list
        .filter((x) => x && typeof x.id === "string" && (x.source === "newapi" || x.source === "ollama"))
        .map((x) => ({ id: x.id, source: x.source, legacy: Boolean(x.legacy) }));
      setModels(ms);
      const def = typeof d?.chat_model_id === "string" ? d.chat_model_id : "";
      setModelId((cur) => cur || def);
      const errs = m?.errors || {};
      const newapiErr = typeof errs?.newapi === "string" && errs.newapi ? errs.newapi : null;
      if (newapiErr) {
        setStatus(newapiErr);
        window.setTimeout(() => setStatus(null), 2500);
      }
    } catch (e: any) {
      setStatus(String(e?.message || e || "加载模型失败"));
      window.setTimeout(() => setStatus(null), 2500);
    }
  }, []);

  React.useEffect(() => {
    loadModels().catch(() => null);
  }, [loadModels]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    const nextMsgs = [...msgs, { role: "user", content: text } as ChatMsg];
    setMsgs(nextMsgs);
    setBusy(true);
    try {
      const legacyOllama = modelId.startsWith("ollama:");
      if (legacyOllama) {
        const m = modelId.slice("ollama:".length) || "default";
        const r = await api.post("/legacy/ollama/chat", { model: m, messages: nextMsgs });
        const out = r?.choices?.[0]?.message?.content ?? "";
        setMsgs((xs) => [...xs, { role: "assistant", content: String(out) }]);
      } else {
        const r = await api.post("/v1/chat/completions", { model: modelId || undefined, messages: nextMsgs, stream: false });
        const out = r?.choices?.[0]?.message?.content ?? "";
        setMsgs((xs) => [...xs, { role: "assistant", content: String(out) }]);
      }
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "assistant", content: `请求失败：${String(e?.message || e)}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-w-0 rounded-2xl border border-[#87CEEB]/35 bg-white/70 backdrop-blur">
        <div className="flex items-center justify-between border-b border-[#87CEEB]/25 px-4 py-3">
          <div className="text-sm font-semibold text-slate-900">对话（New API）</div>
          <div className="flex items-center gap-3">
            {status ? <div className="text-xs text-slate-600">{status}</div> : null}
            <div className="text-xs text-slate-600">{getApiKey() ? "已鉴权" : "未鉴权"}</div>
          </div>
        </div>

        <div className="flex max-h-[calc(100vh-240px)] flex-col gap-3 overflow-auto p-4">
          {msgs.length ? (
            msgs.map((m, i) => (
              <div
                key={i}
                className={[
                  "rounded-2xl border px-3 py-2 text-sm leading-relaxed shadow-sm",
                  m.role === "user"
                    ? "border-[#87CEEB]/25 bg-[#F0F7FF]"
                    : "border-[#FFB6C1]/35 bg-white"
                ].join(" ")}
              >
                <div className="mb-1 text-[11px] text-slate-500">{m.role}</div>
                <div className="whitespace-pre-wrap text-slate-900">{m.content}</div>
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-500">输入一句话开始。</div>
          )}
        </div>

        <div className="border-t border-[#87CEEB]/25 p-4">
          <textarea
            className="min-h-[96px] w-full rounded-2xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#FFB6C1]"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="像在 IDE 里一样输入…"
          />
          <div className="mt-3 flex items-center gap-2">
            <button
              className="rounded-2xl bg-[#FFB6C1] px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD] disabled:opacity-60"
              onClick={send}
              disabled={busy}
            >
              {busy ? "发送中…" : "发送"}
            </button>
            <select
              className="ml-auto max-w-[220px] rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-xs text-slate-700"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
            >
              <option value="">(使用默认模型)</option>
              {models
                .filter((m) => m.source === "newapi")
                .map((m) => (
                  <option key={`newapi:${m.id}`} value={m.id}>
                    {m.id}
                  </option>
                ))}
              {models.some((m) => m.source === "ollama") ? <option disabled value="__sep__">────────</option> : null}
              {models
                .filter((m) => m.source === "ollama")
                .map((m) => (
                  <option key={`ollama:${m.id}`} value={`ollama:${m.id}`}>
                    (遗留) {m.id}
                  </option>
                ))}
            </select>
          </div>
        </div>
      </div>
  );
}
