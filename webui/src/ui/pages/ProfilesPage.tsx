import React from "react";
import { api } from "../lib/api";
import { usePrompt } from "../components/PromptProvider";

type Profile = {
  id: string;
  name: string;
  tier: "L1" | "L2" | "L3";
  model_alias_id: string;
  system_prompt: string;
  params: Record<string, any>;
  tools_enabled: boolean;
  private_memory_enabled: boolean;
};

export function ProfilesPage() {
  const [profiles, setProfiles] = React.useState<Profile[]>([]);
  const { prompt } = usePrompt();
  const [defaultProfileId, setDefaultProfileId] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    const r = await api.get("/api/control/profiles");
    setProfiles(r.profiles || []);
    setDefaultProfileId(r.default_profile_id ?? null);
  }, []);

  React.useEffect(() => {
    reload().catch(() => null);
  }, [reload]);

  const upsert = async (p: Profile) => {
    await api.post("/api/control/profiles", p);
    await reload();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="text-lg font-semibold text-slate-900">Profiles</div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-2 text-xs text-slate-600">默认 Profile</div>
        <select
          className="w-full rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900"
          value={defaultProfileId ?? ""}
          onChange={async (e) => {
            const v = e.target.value || null;
            setDefaultProfileId(v);
            await api.post("/api/control/profiles/default", { default_profile_id: v });
            await reload();
          }}
        >
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.tier})
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {profiles.map((p) => (
          <div key={p.id} className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-slate-900">
                {p.name} <span className="text-xs text-slate-500">({p.id})</span>
              </div>
              <button
                className="rounded-xl border border-[#87CEEB]/35 bg-white px-2 py-1 text-xs text-slate-900 hover:bg-white/80"
                onClick={async () => {
                  await api.del(`/api/control/profiles/${encodeURIComponent(p.id)}`);
                  await reload();
                }}
              >
                删除
              </button>
            </div>

            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-1">
                <div className="text-xs text-slate-600">Tier</div>
                <select
                  className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900"
                  value={p.tier}
                  onChange={async (e) => {
                    const next = { ...p, tier: e.target.value as any };
                    setProfiles((xs) => xs.map((x) => (x.id === p.id ? next : x)));
                    await upsert(next);
                  }}
                >
                  <option value="L1">L1</option>
                  <option value="L2">L2</option>
                  <option value="L3">L3</option>
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <div className="text-xs text-slate-600">Model Alias</div>
                <input
                  className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900"
                  value={p.model_alias_id}
                  onChange={(e) => setProfiles((xs) => xs.map((x) => (x.id === p.id ? { ...x, model_alias_id: e.target.value } : x)))}
                  onBlur={() => upsert(p)}
                />
              </label>
            </div>

            <div className="mt-3">
              <div className="mb-2 text-xs text-slate-600">System Prompt</div>
              <textarea
                className="min-h-[120px] w-full rounded-xl border border-[#87CEEB]/35 bg-white p-3 text-sm text-slate-900"
                value={p.system_prompt ?? ""}
                onChange={(e) => setProfiles((xs) => xs.map((x) => (x.id === p.id ? { ...x, system_prompt: e.target.value } : x)))}
                onBlur={() => upsert(p)}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">新增 Profile</div>
        <button
          className="rounded-2xl bg-[#FFB6C1] px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD]"
          onClick={async () => {
            const id = (await prompt({ title: "新增 Profile", description: "输入唯一 id（例如 l2_default）", placeholder: "profile id", defaultValue: "" }))?.trim();
            if (!id) return;
            const name = (await prompt({ title: "显示名称", defaultValue: id }))?.trim() || id;
            const p: Profile = {
              id,
              name,
              tier: "L2",
              model_alias_id: "default",
              system_prompt: "",
              params: {},
              tools_enabled: true,
              private_memory_enabled: true
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
