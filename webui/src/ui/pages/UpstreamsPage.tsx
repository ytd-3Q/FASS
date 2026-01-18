import React from "react";
import { api } from "../lib/api";

type Upstreams = {
  newapi_base_url: string;
  newapi_api_key: string;
  newapi_has_key: boolean;
  ollama_base_url: string;
  ollama_api_key: string;
  ollama_has_key: boolean;
};

export function UpstreamsPage() {
  const [state, setState] = React.useState<Upstreams>({
    newapi_base_url: "",
    newapi_api_key: "",
    newapi_has_key: false,
    ollama_base_url: "http://localhost:11434",
    ollama_api_key: "",
    ollama_has_key: false
  });
  const [busy, setBusy] = React.useState(false);
  const [status, setStatus] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    setBusy(true);
    try {
      const r = await api.get("/api/config/upstreams");
      setState((s) => ({
        ...s,
        newapi_base_url: String(r?.newapi_base_url || ""),
        newapi_has_key: Boolean(r?.newapi_has_key),
        ollama_base_url: String(r?.ollama_base_url || "http://localhost:11434"),
        ollama_has_key: Boolean(r?.ollama_has_key),
        newapi_api_key: "",
        ollama_api_key: ""
      }));
      setStatus(null);
    } catch (e: any) {
      setStatus(String(e?.message || e || "加载失败"));
    } finally {
      setBusy(false);
    }
  }, []);

  React.useEffect(() => {
    reload().catch(() => null);
  }, [reload]);

  const save = async () => {
    setBusy(true);
    try {
      await api.post("/api/config/upstreams", {
        newapi_base_url: state.newapi_base_url || null,
        newapi_api_key: state.newapi_api_key ? state.newapi_api_key : null,
        ollama_base_url: state.ollama_base_url || null,
        ollama_api_key: state.ollama_api_key ? state.ollama_api_key : null
      });
      await reload();
      setStatus("已保存");
      window.setTimeout(() => setStatus(null), 2000);
    } catch (e: any) {
      setStatus(String(e?.message || e || "保存失败"));
    } finally {
      setBusy(false);
    }
  };

  const testFetch = async () => {
    setBusy(true);
    try {
      const r = await api.get("/api/models/list");
      const n = (r?.items || []).filter((x: any) => x?.source === "newapi").length;
      const o = (r?.items || []).filter((x: any) => x?.source === "ollama").length;
      setStatus(`模型拉取成功：New API ${n} · Ollama(遗留) ${o}`);
      window.setTimeout(() => setStatus(null), 2500);
    } catch (e: any) {
      setStatus(String(e?.message || e || "拉取失败"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="text-lg font-semibold text-slate-900">Upstreams</div>
        {status ? <div className="text-sm text-slate-600">{status}</div> : null}
        <div className="flex-1" />
        <button
          className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-white/80 disabled:opacity-60"
          onClick={reload}
          disabled={busy}
        >
          刷新
        </button>
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">New API</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1">
            <div className="text-xs text-slate-600">地址</div>
            <input
              className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#FFB6C1]"
              value={state.newapi_base_url}
              onChange={(e) => setState((s) => ({ ...s, newapi_base_url: e.target.value }))}
              placeholder="https://your-newapi.example.com"
            />
          </label>
          <label className="flex flex-col gap-1">
            <div className="text-xs text-slate-600">Key（必填） {state.newapi_has_key ? <span className="text-slate-500">已设置</span> : null}</div>
            <input
              className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#FFB6C1]"
              value={state.newapi_api_key}
              onChange={(e) => setState((s) => ({ ...s, newapi_api_key: e.target.value }))}
              placeholder="sk-..."
              type="password"
            />
          </label>
        </div>
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">Ollama（遗留）</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1">
            <div className="text-xs text-slate-600">地址</div>
            <input
              className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#FFB6C1]"
              value={state.ollama_base_url}
              onChange={(e) => setState((s) => ({ ...s, ollama_base_url: e.target.value }))}
              placeholder="http://localhost:11434"
            />
          </label>
          <label className="flex flex-col gap-1">
            <div className="text-xs text-slate-600">Key（可选） {state.ollama_has_key ? <span className="text-slate-500">已设置</span> : null}</div>
            <input
              className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-[#FFB6C1]"
              value={state.ollama_api_key}
              onChange={(e) => setState((s) => ({ ...s, ollama_api_key: e.target.value }))}
              placeholder="可选"
              type="password"
            />
          </label>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-white/80 disabled:opacity-60"
          onClick={testFetch}
          disabled={busy}
        >
          测试拉取模型列表
        </button>
        <div className="flex-1" />
        <button
          className="rounded-2xl bg-[#FFB6C1] px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD] disabled:opacity-60"
          onClick={save}
          disabled={busy}
        >
          保存
        </button>
      </div>
    </div>
  );
}

