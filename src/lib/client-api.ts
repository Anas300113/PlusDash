export type LearnerProfile = { displayName: string; streakDays: number };

export type ApiError = { error: string; code?: string };

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: "GET", cache: "no-store", credentials: "same-origin" });
  const payload = await response.json().catch(() => null) as (T & ApiError) | null;
  if (!response.ok || payload === null) throw new Error(payload && "error" in payload ? payload.error : "We couldn’t load this just now. Please try again.");
  return payload;
}

export async function apiWrite<T>(path: string, csrf: string, method: "POST" | "PATCH", body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    cache: "no-store",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "x-plus11-csrf": csrf },
    body: JSON.stringify(body ?? {}),
  });
  const payload = await response.json().catch(() => null) as (T & ApiError) | null;
  if (!response.ok || payload === null) throw new Error(payload && "error" in payload ? payload.error : "We couldn’t save this just now. Please try again.");
  return payload;
}
