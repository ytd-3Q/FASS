import React from "react";
import { api } from "../lib/api";

export function ModelCatalogPage() {
  const [defaultProviderId, setDefaultProviderId] = React.useState<string | null>(null);
  const [items, setItems] = React.useState<Array<{ model_id: string; status: string }>>([]);
  const [presets, setPresets] = React.useState<any[]>([]);
  const [status, setStatus] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    const p = await api.get("/api/control/providers");
    const pid = p.default_provider_id ?? null;
    setDefaultProviderId(pid);
    if (pid) {
      const c = await api.get(`/api/control/model_catalog?provider_id=${encodeURIComponent(pid)}&status=online`);
      setItems(c.items || []);
      const lp = await api.get("/api/control/layer_presets");
      setPresets(lp.items || []);
    } else {
      setItems([]);
      setPresets([]);
    }
  }, []);

  React.useEffect(() => {
    reload().catch(() => null);
  }, [reload]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <div className="text-lg font-semibold text-slate-900">模型库（ModelCatalog）</div>
        {status ? <div className="text-sm text-slate-600">{status}</div> : null}
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm text-slate-700">当前默认 Provider：{defaultProviderId ?? "未设置"}</div>
          <button
            className="rounded-2xl bg-[#FFB6C1] px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD] disabled:opacity-60"
            disabled={!defaultProviderId}
            onClick={async () => {
              if (!defaultProviderId) return;
              try {
                setStatus("同步中…");
                await api.post("/api/control/model_catalog/sync", { provider_id: defaultProviderId });
                setStatus("同步完成");
                await reload();
              } catch (e: any) {
                setStatus(String(e?.message || e));
              } finally {
                window.setTimeout(() => setStatus(null), 2500);
              }
            }}
          >
            同步模型库
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
          <div className="mb-2 text-sm font-semibold text-slate-900">可用模型（在线）</div>
          <div className="max-h-[320px] overflow-auto rounded-2xl border border-[#87CEEB]/25 bg-white p-3 text-sm text-slate-800">
            {items.length ? (
              <div className="flex flex-col gap-1">
                {items.map((it) => (
                  <div key={it.model_id} className="flex items-center justify-between">
                    <div className="truncate">{it.model_id}</div>
                    <div className="text-xs text-slate-500">{it.status}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-slate-500">暂无。先配置 Provider 并同步。</div>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
          <div className="mb-2 text-sm font-semibold text-slate-900">LayerPreset（自动匹配结果）</div>
          <div className="flex flex-col gap-2">
            {presets.length ? (
              presets.map((p) => (
                <div key={p.layer} className="rounded-2xl border border-[#87CEEB]/25 bg-white p-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-900">{p.layer}</div>
                    <div className="text-xs text-slate-500">{p.selected_model_id ?? "未选择"}</div>
                  </div>
                  {p.selection_reason ? (
                    <div className="mt-2 text-xs text-slate-700">
                      <div>confidence: {p.selection_reason.confidence_score}</div>
                      <div className="mt-1">factors: {(p.selection_reason.decision_factors || []).join(", ")}</div>
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-500">暂无。同步模型库后自动生成。</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

