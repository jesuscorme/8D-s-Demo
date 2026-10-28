"use client";

import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

type Options = { method?: string; body?: unknown; form?: FormData };

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = { "x-d8-client": "web" };
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`/api${path}`, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, cache: "no-store" });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/auth/login") && typeof window !== "undefined") {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    }
    throw new ApiError(res.status, data.code ?? "error", data.message ?? `Error ${res.status}`, data.details);
  }
  return data as T;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.details;
    if (Array.isArray(d) && d.length) {
      const items = d.map((x) => (typeof x === "string" ? x : x?.field ? `${x.field}: ${x.message}` : JSON.stringify(x)));
      return `${e.message} ${items.join(" · ")}`;
    }
    return e.message;
  }
  return e instanceof Error ? e.message : "Error inesperado";
}

/** Carga datos con estados de carga/error y recarga manual. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, setData, error, loading, reload };
}
