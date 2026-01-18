import React from "react";
import { ApiKeyBanner } from "../components/ApiKeyBanner";
import { ModelsPage } from "./ModelsPage";
import { UpstreamsPage } from "./UpstreamsPage";

type TabId = "api" | "upstreams" | "models";

export function SettingsPage() {
  const [tab, setTab] = React.useState<TabId>("api");

  const tabs: Array<{ id: TabId; name: string }> = [
    { id: "api", name: "API Key" },
    { id: "upstreams", name: "Upstreams" },
    { id: "models", name: "Models" }
  ];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-3 backdrop-blur">
        <div className="mb-2 text-sm font-semibold text-slate-900">设置</div>
        <div className="flex flex-col gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={[
                "rounded-xl px-3 py-2 text-left text-sm transition",
                tab === t.id ? "bg-[#FFB6C1] text-slate-900" : "text-slate-700 hover:bg-white"
              ].join(" ")}
              onClick={() => setTab(t.id)}
            >
              {t.name}
            </button>
          ))}
        </div>
      </div>

      <div className="min-w-0 rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        {tab === "api" ? (
          <div className="flex flex-col gap-4">
            <div>
              <div className="text-lg font-semibold text-slate-900">API Key</div>
              <div className="mt-1 text-sm text-slate-600">访问受保护接口与 /v1/* 所需的凭证（保存在浏览器本地）。</div>
            </div>
            <ApiKeyBanner />
          </div>
        ) : null}

        {tab === "models" ? <ModelsPage /> : null}
        {tab === "upstreams" ? <UpstreamsPage /> : null}
      </div>
    </div>
  );
}
