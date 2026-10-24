"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet, type LearnerProfile } from "@/lib/client-api";

type SessionStatus = "loading" | "guest" | "authenticated" | "error";
type SessionContextValue = {
  status: SessionStatus;
  user: LearnerProfile | null;
  csrfToken: string | null;
  error: string | null;
  refresh: () => Promise<void>;
};

type SessionResponse = { user: LearnerProfile | null; csrfToken: string | null };
const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<LearnerProfile | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const result = await apiGet<SessionResponse>("/api/auth/session");
      setUser(result.user);
      setCsrfToken(result.csrfToken);
      setStatus(result.user ? "authenticated" : "guest");
    } catch (reason) {
      setUser(null);
      setCsrfToken(null);
      setError(reason instanceof Error ? reason.message : "We couldn’t check your account just now.");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    let active = true;
    void apiGet<SessionResponse>("/api/auth/session").then((result) => {
      if (!active) return;
      setUser(result.user);
      setCsrfToken(result.csrfToken);
      setStatus(result.user ? "authenticated" : "guest");
    }).catch((reason: unknown) => {
      if (!active) return;
      setUser(null);
      setCsrfToken(null);
      setError(reason instanceof Error ? reason.message : "We couldn’t check your account just now.");
      setStatus("error");
    });
    return () => { active = false; };
  }, []);

  const value = useMemo(() => ({ status, user, csrfToken, error, refresh }), [status, user, csrfToken, error, refresh]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider.");
  return context;
}

export function startSignIn(): void {
  const origin = window.location.origin;
  const destination = new URL(`/api/auth/start?origin=${encodeURIComponent(origin)}`, origin);
  window.location.assign(destination.toString());
}
