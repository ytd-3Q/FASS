import React from "react";
import { api } from "../lib/api";
import { usePrompt } from "../components/PromptProvider";

type Job = {
  id: number;
  query: string;
  collection: string;
  status: string;
  scheduled_at_unix_ms: number;
  error?: string | null;
  result_json?: string | null;
};

export function AutomationsPage() {
  const [searxng, setSearxng] = React.useState<string>("");
  const [jobs, setJobs] = React.useState<Job[]>([]);
  const [status, setStatus] = React.useState<string | null>(null);
  const { prompt } = usePrompt();

  const reload = React.useCallback(async () => {
    const w = await api.get("/api/control/websearch");
    setSearxng(w.searxng_base_url ?? "");
    const j = await api.get("/api/automations/research/jobs");
    setJobs(j.jobs || []);
  }, []);

  React.useEffect(() => {
    reload().catch(() => null);
  }, [reload]);

  return (
    <div className="flex flex-col gap-4">
      <div className="text-lg font-semibold text-slate-900">Automations</div>

      {status ? <div className="text-sm text-slate-600">{status}</div> : null}

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-2 text-sm font-medium text-slate-900">Web Search（SearxNG）</div>
        <div className="text-xs text-slate-600">用于自动 research job 的联网检索。示例：http://searxng:8080</div>
        <div className="mt-3 flex flex-col gap-2 md:flex-row md:items-center">
          <input
            className="w-full flex-1 rounded-2xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900"
            value={searxng}
            onChange={(e) => setSearxng(e.target.value)}
            placeholder="SearxNG Base URL"
          />
          <button
            className="rounded-2xl bg-[#FFB6C1] px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD]"
            onClick={async () => {
              try {
                await api.post("/api/control/websearch", { searxng_base_url: searxng.trim() ? searxng.trim() : null });
                setStatus("已保存");
              } catch (e: any) {
                setStatus(String(e?.message || e));
              } finally {
                window.setTimeout(() => setStatus(null), 1200);
              }
            }}
          >
            保存
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">手动触发 Research</div>
        <button
          className="rounded-2xl bg-[#FFB6C1] px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD]"
          onClick={async () => {
            const q = (await prompt({ title: "手动入队 Research", placeholder: "输入 query", defaultValue: "" }))?.trim();
            if (!q) return;
            try {
              const r = await api.post("/api/automations/research/enqueue", { query: q, collection: "shared" });
              setStatus(JSON.stringify(r));
              await reload();
            } catch (e: any) {
              setStatus(String(e?.message || e));
            }
          }}
        >
          入队
        </button>
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">Dreaming（梦境模式）</div>
        <button
          className="rounded-2xl bg-[#FFB6C1] px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD]"
          onClick={async () => {
            try {
              setStatus("执行中…");
              const r = await api.post("/api/automations/dreaming/run", { max_items: 10, collection: "shared" });
              setStatus(JSON.stringify(r));
            } catch (e: any) {
              setStatus(String(e?.message || e));
            }
          }}
        >
          立即执行
        </button>
      </div>

      <div className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-medium text-slate-900">Research Jobs</div>
        <div className="flex flex-col gap-2">
          {jobs.length ? (
            jobs.map((j) => (
              <div key={j.id} className="rounded-2xl border border-[#87CEEB]/25 bg-white p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm text-slate-900">
                    #{j.id} <span className="text-slate-500">{j.status}</span>
                  </div>
                  <div className="text-xs text-slate-500">{new Date(j.scheduled_at_unix_ms).toLocaleString()}</div>
                </div>
                <div className="mt-1 text-sm text-slate-700">{j.query}</div>
                {j.error ? <div className="mt-2 text-xs text-rose-600">error: {j.error}</div> : null}
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-500">暂无。</div>
          )}
        </div>
      </div>
    </div>
  );
}
