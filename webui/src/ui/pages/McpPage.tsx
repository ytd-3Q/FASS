import React from "react";
import { api } from "../lib/api";
import { usePrompt } from "../components/PromptProvider";

type Tool = {
  name: string;
  description: string;
  parameters: any;
  enabled: boolean;
  read_only: boolean;
  dangerous: boolean;
  timeout_seconds: number;
};

export function McpPage() {
  const [tools, setTools] = React.useState<Tool[]>([]);
  const [status, setStatus] = React.useState<string | null>(null);
  const { prompt } = usePrompt();

  const reload = React.useCallback(async () => {
    const r = await api.get("/api/mcp/tools");
    setTools(r.tools || []);
  }, []);

  React.useEffect(() => {
    reload().catch(() => null);
  }, [reload]);

  const toggle = async (t: Tool, enabled: boolean) => {
    await api.post(`/api/mcp/tools/${encodeURIComponent(t.name)}/enable`, { enabled });
    await reload();
  };

  const run = async (t: Tool) => {
    const raw =
      (await prompt({
        title: "测试执行参数",
        description: "输入 arguments JSON（Ctrl+Enter 提交）。留空将按 {} 处理。",
        defaultValue: "{}",
        multiline: true
      })) ?? null;
    if (raw === null) return;
    let args: any = {};
    try {
      args = raw.trim() ? JSON.parse(raw) : {};
    } catch {
      setStatus("arguments JSON 无效");
      window.setTimeout(() => setStatus(null), 1200);
      return;
    }
    try {
      setStatus("执行中…");
      const r = await api.post("/api/mcp/execute", { tool_name: t.name, arguments: args });
      setStatus(JSON.stringify(r, null, 2));
    } catch (e: any) {
      setStatus(String(e?.message || e));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="text-lg font-semibold text-slate-900">MCP Toolbox</div>
        <button
          className="rounded-xl border border-[#87CEEB]/35 bg-white px-2 py-1 text-xs text-slate-900 hover:bg-white/80"
          onClick={() => reload().catch(() => null)}
        >
          刷新
        </button>
      </div>

      {status ? (
        <pre className="max-h-[260px] overflow-auto rounded-2xl border border-white/10 bg-zinc-950/45 p-4 text-xs text-zinc-200 backdrop-blur-xl">
          {status}
        </pre>
      ) : null}

      <div className="grid grid-cols-1 gap-4">
        {tools.map((t) => (
          <div key={t.name} className="rounded-2xl border border-[#87CEEB]/35 bg-white/70 p-4 backdrop-blur">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-slate-900">{t.name}</div>
                <div className="mt-1 text-xs text-slate-600">
                  {t.read_only ? "read-only" : "mutable"} · {t.dangerous ? "dangerous" : "safe"} · timeout {t.timeout_seconds}s
                </div>
                <div className="mt-2 text-sm text-slate-700">{t.description}</div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-xl border border-[#87CEEB]/35 bg-white px-2 py-1 text-xs text-slate-900 hover:bg-white/80"
                  onClick={() => toggle(t, !t.enabled).catch(() => null)}
                >
                  {t.enabled ? "禁用" : "启用"}
                </button>
                <button
                  className="rounded-xl bg-[#FFB6C1] px-2 py-1 text-xs font-semibold text-slate-900 hover:bg-[#F8C3CD] disabled:opacity-60"
                  disabled={!t.enabled}
                  onClick={() => run(t).catch(() => null)}
                >
                  测试执行
                </button>
              </div>
            </div>
            <div className="mt-3">
              <div className="mb-1 text-xs text-slate-600">Parameters</div>
              <pre className="max-h-[180px] overflow-auto rounded-2xl border border-[#87CEEB]/35 bg-white p-3 text-xs text-slate-900">
                {JSON.stringify(t.parameters, null, 2)}
              </pre>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
