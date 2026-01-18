export function getApiKey(): string | null {
  try {
    return localStorage.getItem("fass_api_key");
  } catch {
    return null;
  }
}

export function setApiKey(v: string | null): void {
  try {
    if (v) localStorage.setItem("fass_api_key", v);
    else localStorage.removeItem("fass_api_key");
  } catch {
    return;
  }
}

function resolveUrl(path: string): string {
  const base = (import.meta as any).env?.VITE_API_BASE_URL as string | undefined;
  if (!base) return path;
  if (/^https?:\/\//i.test(path)) return path;
  return String(base).replace(/\/$/, "") + (path.startsWith("/") ? path : `/${path}`);
}

async function requestJson(method: string, path: string, body?: unknown): Promise<any> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const k = getApiKey();
  if (k) headers["Authorization"] = `Bearer ${k}`;
  const res = await fetch(resolveUrl(path), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

export const api = {
  get: (path: string) => requestJson("GET", path),
  post: (path: string, body: unknown) => requestJson("POST", path, body),
  del: async (path: string) => {
    const headers: Record<string, string> = {};
    const k = getApiKey();
    if (k) headers["Authorization"] = `Bearer ${k}`;
    const res = await fetch(resolveUrl(path), { method: "DELETE", headers });
    if (!res.ok) throw new Error(await res.text());
    return await res.json();
  }
};
