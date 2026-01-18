import React from "react";
import { api } from "../lib/api";

type NewApiModel = { id: string };
type ModelDefaults = { chat_model_id: string | null; embedding_model_id: string | null };

export function ModelsPage() {
  const [models, setModels] = React.useState<NewApiModel[]>([]);
  const [defaults, setDefaults] = React.useState<ModelDefaults>({ chat_model_id: null, embedding_model_id: null });
  const [draft, setDraft] = React.useState<ModelDefaults>({ chat_model_id: null, embedding_model_id: null });
  const [query, setQuery] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [status, setStatus] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    setLoading(true);
    try {
      const [m, d] = await Promise.all([api.get("/api/models/list"), api.get("/api/config/models")]);
      const list = (m?.items || []) as any[];
      setModels(list.filter((x) => x && x.source === "newapi" && typeof x.id === "string").map((x) => ({ id: x.id })));
      const errs = m?.errors || {};
      const newapiErr = typeof errs?.newapi === "string" && errs.newapi ? errs.newapi : null;
      const ollamaErr = typeof errs?.ollama === "string" && errs.ollama ? errs.ollama : null;
      if (newapiErr || ollamaErr) {
        setStatus(`New API: ${newapiErr ?? "ok"} · Ollama(遗留): ${ollamaErr ?? "ok"}`);
      } else {
        setStatus(null);
      }
      const nextDefaults: ModelDefaults = {
        chat_model_id: typeof d?.chat_model_id === "string" ? d.chat_model_id : null,
        embedding_model_id: typeof d?.embedding_model_id === "string" ? d.embedding_model_id : null
      };
      setDefaults(nextDefaults);
      setDraft(nextDefaults);
    } catch (e: any) {
      setStatus(String(e?.message || e || "加载失败"));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    reload().catch(() => null);
  }, [reload]);

  const saveDefaults = async () => {
    setLoading(true);
    try {
      await api.post("/api/config/models", {
        chat_model_id: draft.chat_model_id,
        embedding_model_id: draft.embedding_model_id
      });
      await reload();
      setStatus("已保存");
      window.setTimeout(() => setStatus(null), 2000);
    } catch (e: any) {
      setStatus(String(e?.message || e || "保存失败"));
    } finally {
      setLoading(false);
    }
  };

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models;
    return models.filter((m) => m.id.toLowerCase().includes(q));
  }, [models, query]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="text-lg font-semibold text-slate-900">Models (New API)</div>
        {status ? <div className="text-sm text-slate-600">{status}</div> : null}
        <div className="flex-1" />
        <button
          className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-white/80 disabled:opacity-60"
          onClick={() => reload()}
          disabled={loading}
        >
          刷新
        </button>
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">默认模型</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1">
            <div className="text-xs text-slate-600">默认 Chat 模型</div>
            <select
              className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 disabled:opacity-60"
              value={draft.chat_model_id ?? ""}
              disabled={loading || models.length === 0}
              onChange={(e) => setDraft((d) => ({ ...d, chat_model_id: e.target.value || null }))}
            >
              <option value="">(未设置)</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <div className="text-xs text-slate-600">默认 Embedding 模型</div>
            <select
              className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 disabled:opacity-60"
              value={draft.embedding_model_id ?? ""}
              disabled={loading || models.length === 0}
              onChange={(e) => setDraft((d) => ({ ...d, embedding_model_id: e.target.value || null }))}
            >
              <option value="">(未设置)</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <div className="text-xs text-slate-500">
            当前：chat={defaults.chat_model_id ?? "-"} · embedding={defaults.embedding_model_id ?? "-"}
          </div>
          <div className="flex-1" />
          <button
            className="rounded-2xl bg-[#FFB6C1] px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD] disabled:opacity-60"
            onClick={saveDefaults}
            disabled={loading}
          >
            保存
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 flex items-center gap-3">
          <div className="text-sm font-medium text-slate-900">模型列表</div>
          <input
            className="w-full max-w-[360px] rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#FFB6C1]"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索 model id…"
          />
          <div className="text-xs text-slate-500">{filtered.length} / {models.length}</div>
        </div>
        <div className="max-h-[52vh] overflow-auto rounded-2xl border border-[#87CEEB]/25 bg-white p-2">
          {filtered.length ? (
            <div className="flex flex-col">
              {filtered.map((m) => (
                <div key={m.id} className="rounded-xl px-3 py-2 text-sm text-slate-900 hover:bg-[#F0F7FF]">
                  {m.id}
                </div>
              ))}
            </div>
          ) : (
            <div className="p-3 text-sm text-slate-500">{loading ? "加载中…" : "暂无模型"}</div>
          )}
        </div>
      </div>
    </div>
  );
}
