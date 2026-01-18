import React from "react";
import { api } from "../lib/api";
import { usePrompt } from "../components/PromptProvider";

type Provider = {
  id: string;
  name: string;
  type: "openai_compat" | "ollama";
  base_url: string;
  enabled: boolean;
  timeout_seconds: number;
  auth: { type: "none" | "bearer" | "header"; header_name?: string | null; has_token?: boolean; token?: string | null };
  extra_headers: Record<string, string>;
};

export function ProvidersPage() {
  const [providers, setProviders] = React.useState<Provider[]>([]);
  const [defaultProviderId, setDefaultProviderId] = React.useState<string | null>(null);
  const [runtime, setRuntime] = React.useState<Record<string, any>>({});
  const [status, setStatus] = React.useState<string | null>(null);
  const { prompt } = usePrompt();

  const reload = React.useCallback(async () => {
    const r = await api.get("/api/control/providers");
    setProviders(r.providers || []);
    setDefaultProviderId(r.default_provider_id ?? null);
    setRuntime(r.runtime || {});
  }, []);

  React.useEffect(() => {
    reload().catch(() => null);
  }, [reload]);

  const upsert = async (p: Provider) => {
    await api.post("/api/control/providers", p);
    await reload();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="text-lg font-semibold text-slate-900">Providers</div>
        {status ? <div className="text-sm text-slate-600">{status}</div> : null}
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-2 text-xs text-slate-600">默认 Provider</div>
        <select
          className="w-full rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900"
          value={defaultProviderId ?? ""}
          onChange={async (e) => {
            const v = e.target.value || null;
            setDefaultProviderId(v);
            await api.post("/api/control/defaults", { default_provider_id: v });
            await reload();
          }}
        >
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.id})
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {providers.map((p) => {
          const h = runtime?.[p.id]?.health;
          const c = runtime?.[p.id]?.circuit;
          return (
            <div key={p.id} className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-900">
                    {p.name} <span className="text-xs text-slate-500">({p.id})</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    {p.type} · {h?.status ?? "unknown"} · {h?.latency_ms ?? "-"}ms · circuit {c?.state ?? "closed"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="rounded-xl border border-[#87CEEB]/35 bg-white px-2 py-1 text-xs text-slate-900 hover:bg-white/80"
                    onClick={async () => {
                      try {
                        setStatus("测试中…");
                        await api.post(`/api/control/providers/${encodeURIComponent(p.id)}/test`, {});
                        setStatus("测试成功");
                      } catch {
                        setStatus("测试失败");
                      } finally {
                        window.setTimeout(() => setStatus(null), 1200);
                      }
                    }}
                  >
                    测试
                  </button>
                  <button
                    className="rounded-xl border border-[#87CEEB]/35 bg-white px-2 py-1 text-xs text-slate-900 hover:bg-white/80"
                    onClick={async () => {
                      await api.del(`/api/control/providers/${encodeURIComponent(p.id)}`);
                      await reload();
                    }}
                  >
                    删除
                  </button>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <div className="text-xs text-slate-600">Base URL</div>
                  <input
                    className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900"
                    value={p.base_url}
                    onChange={(e) => setProviders((ps) => ps.map((x) => (x.id === p.id ? { ...x, base_url: e.target.value } : x)))}
                    onBlur={() => upsert(p)}
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <div className="text-xs text-slate-600">Enabled</div>
                  <select
                    className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900"
                    value={p.enabled ? "1" : "0"}
                    onChange={async (e) => {
                      const enabled = e.target.value === "1";
                      const next = { ...p, enabled };
                      setProviders((ps) => ps.map((x) => (x.id === p.id ? next : x)));
                      await upsert(next);
                    }}
                  >
                    <option value="1">启用</option>
                    <option value="0">禁用</option>
                  </select>
                </label>
              </div>
            </div>
          );
        })}
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">新增 Provider</div>
        <button
          className="rounded-2xl bg-[#FFB6C1] px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD]"
          onClick={async () => {
            const id = (await prompt({ title: "新增 Provider", description: "输入唯一 id（例如 newapi、openai、ollama）", placeholder: "id", defaultValue: "" }))?.trim();
            if (!id) return;
            const base = (await prompt({ title: "Base URL", placeholder: "https://newapi.example.com 或 http://ollama:11434", defaultValue: "" }))?.trim();
            if (!base) return;
            const name = (await prompt({ title: "显示名称", defaultValue: id }))?.trim() || id;
            const typeRaw = (await prompt({ title: "类型", description: "openai_compat 或 ollama", defaultValue: "openai_compat" }))?.trim();
            const type = (typeRaw === "ollama" ? "ollama" : "openai_compat") as any;
            const token = (await prompt({ title: "Token（可选）", description: "留空表示不设置（如 New-API/OpenAI token）", defaultValue: "", kind: "password" })) ?? "";
            const p: Provider = {
              id,
              name,
              type,
              base_url: base,
              enabled: true,
              timeout_seconds: 60,
              auth: { type: token.trim() ? "bearer" : "none", token: token.trim() ? token.trim() : null },
              extra_headers: {}
            };
            await upsert(p);
          }}
        >
          新增
        </button>
      </div>
    </div>
  );
}
