import React from "react";

type PromptOptions = {
  title: string;
  description?: string;
  placeholder?: string;
  defaultValue?: string;
  multiline?: boolean;
  confirmText?: string;
  cancelText?: string;
  kind?: "text" | "password";
  validate?: (value: string) => string | null;
};

type PromptState =
  | {
      open: false;
    }
  | {
      open: true;
      options: PromptOptions;
      value: string;
      error: string | null;
      resolve: (value: string | null) => void;
    };

const PromptContext = React.createContext<{
  prompt: (options: PromptOptions) => Promise<string | null>;
} | null>(null);

export function usePrompt() {
  const ctx = React.useContext(PromptContext);
  if (!ctx) throw new Error("usePrompt must be used within PromptProvider");
  return ctx;
}

export function PromptProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<PromptState>({ open: false });
  const busyRef = React.useRef(false);

  const prompt = React.useCallback(async (options: PromptOptions) => {
    if (busyRef.current) return null;
    busyRef.current = true;
    return await new Promise<string | null>((resolve) => {
      setState({
        open: true,
        options,
        value: options.defaultValue ?? "",
        error: null,
        resolve: (v) => {
          busyRef.current = false;
          resolve(v);
        }
      });
    });
  }, []);

  const close = React.useCallback(
    (value: string | null) => {
      if (!state.open) return;
      const resolve = state.resolve;
      setState({ open: false });
      resolve(value);
    },
    [state]
  );

  const submit = React.useCallback(() => {
    if (!state.open) return;
    const v = state.value;
    const err = state.options.validate?.(v) ?? null;
    if (err) {
      setState({ ...state, error: err });
      return;
    }
    close(v);
  }, [close, state]);

  React.useEffect(() => {
    if (!state.open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(null);
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close, state.open, submit]);

  return (
    <PromptContext.Provider value={{ prompt }}>
      {children}
      {state.open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button className="absolute inset-0 bg-white/60 backdrop-blur-sm" onClick={() => close(null)} />
          <div className="relative w-full max-w-lg rounded-2xl border border-[#87CEEB]/35 bg-white/90 p-4 shadow-[0_18px_50px_rgba(15,23,42,0.12)]">
            <div className="text-sm font-semibold text-slate-900">{state.options.title}</div>
            {state.options.description ? <div className="mt-1 text-xs text-slate-600">{state.options.description}</div> : null}
            <div className="mt-3">
              {state.options.multiline ? (
                <textarea
                  className="min-h-[120px] w-full rounded-xl border border-[#87CEEB]/35 bg-[#F0F7FF] p-3 text-sm text-slate-900 outline-none ring-0 placeholder:text-slate-400 focus:border-[#FFB6C1]"
                  placeholder={state.options.placeholder}
                  value={state.value}
                  onChange={(e) => setState({ ...state, value: e.target.value, error: null })}
                />
              ) : (
                <input
                  className="w-full rounded-xl border border-[#87CEEB]/35 bg-[#F0F7FF] px-3 py-2 text-sm text-slate-900 outline-none ring-0 placeholder:text-slate-400 focus:border-[#FFB6C1]"
                  placeholder={state.options.placeholder}
                  type={state.options.kind === "password" ? "password" : "text"}
                  value={state.value}
                  onChange={(e) => setState({ ...state, value: e.target.value, error: null })}
                  autoFocus
                />
              )}
            </div>
            {state.error ? <div className="mt-2 text-xs text-rose-600">{state.error}</div> : null}
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                className="rounded-xl border border-[#87CEEB]/35 bg-white px-3 py-2 text-sm text-slate-900 hover:bg-white/80"
                onClick={() => close(null)}
              >
                {state.options.cancelText ?? "取消"}
              </button>
              <button
                className="rounded-xl bg-[#FFB6C1] px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-[#F8C3CD]"
                onClick={submit}
              >
                {state.options.confirmText ?? "确定"}
              </button>
            </div>
            <div className="mt-2 text-[11px] text-slate-500">Enter: 换行 / Ctrl+Enter: 提交 / Esc: 取消</div>
          </div>
        </div>
      ) : null}
    </PromptContext.Provider>
  );
}
