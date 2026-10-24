import "server-only";

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { SignJWT, jwtVerify } from "jose";
import { AppError } from "@/lib/errors";

export const SESSION_COOKIE = "webdev_app_session";
export const OAUTH_STATE_COOKIE = "plus11_oauth_state";
const PREVIEW_ORIGIN = "https://8328-ifnbwm75t7qzlecbu3kpi-176ad7c5.us5.manus.computer";
const OAUTH_CALLBACK_PATH = "/api/auth/callback";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

export type LearnerSession = {
  openId: string;
  appId: string;
  name: string;
  iat: number;
};

type OAuthState = { redirectUri: string; nonce: string };

type ManusUserInfo = { openId?: unknown; name?: unknown; email?: unknown };

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Required server configuration ${name} is unavailable.`);
  return value;
}

function secretKey(): Uint8Array {
  return new TextEncoder().encode(requiredEnv("MANUS_JWT_SECRET"));
}

function extraAllowedOrigins(): string[] {
  return (process.env.PLUS11_AUTH_ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function isAllowedPublicOrigin(raw: string): boolean {
  let candidate: URL;
  try {
    candidate = new URL(raw);
  } catch {
    return false;
  }
  if (candidate.username || candidate.password || candidate.pathname !== "/" || candidate.search || candidate.hash) return false;
  const origin = candidate.origin;
  if (origin === PREVIEW_ORIGIN || extraAllowedOrigins().some((allowed) => {
    try { return new URL(allowed).origin === origin && new URL(allowed).pathname === "/"; } catch { return false; }
  })) return candidate.protocol === "https:";
  const localHost = candidate.hostname === "localhost" || candidate.hostname === "127.0.0.1" || candidate.hostname === "[::1]";
  return localHost && candidate.protocol === "http:";
}

export function validatedRequestOrigin(request: Request): URL {
  const raw = request.headers.get("origin");
  if (!raw || !isAllowedPublicOrigin(raw)) throw new AppError("This request origin is not allowed.", 403, "invalid_origin");
  if (request.headers.get("sec-fetch-site") === "cross-site") throw new AppError("Cross-site state changes are not allowed.", 403, "cross_site_request");
  return new URL(raw);
}

export function cookieOptions(publicOrigin: URL, maxAge = COOKIE_MAX_AGE): string {
  const secure = publicOrigin.protocol === "https:";
  const sameSite = secure ? "None" : "Lax";
  return `Path=/; HttpOnly; SameSite=${sameSite}; Max-Age=${maxAge}${secure ? "; Secure" : ""}`;
}

export function readCookie(request: Request, name: string): string | null {
  const header = request.headers.get("cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const equals = part.indexOf("=");
    if (equals < 0) continue;
    if (part.slice(0, equals).trim() === name) {
      const value = part.slice(equals + 1).trim();
      try { return decodeURIComponent(value); } catch { return value; }
    }
  }
  return null;
}

export async function signLearnerSession(user: { openId: string; name: string }): Promise<string> {
  const projectId = requiredEnv("MANUS_PROJECT_ID");
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ openId: user.openId, name: user.name, appId: projectId })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuedAt(now)
    .setExpirationTime(now + COOKIE_MAX_AGE)
    .sign(secretKey());
}

export async function getLearnerSession(request: Request): Promise<{ session: LearnerSession; token: string } | null> {
  const token = readCookie(request, SESSION_COOKIE);
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, secretKey(), { algorithms: ["HS256"], clockTolerance: 5 });
    const projectId = requiredEnv("MANUS_PROJECT_ID");
    if (typeof payload.openId !== "string" || payload.openId.length < 1 || payload.openId.length > 191) return null;
    if (String(payload.appId ?? "") !== projectId || typeof payload.exp !== "number" || payload.exp <= Math.floor(Date.now() / 1000)) return null;
    const name = typeof payload.name === "string" && payload.name.trim() ? payload.name.trim().slice(0, 80) : "Learner";
    return { session: { openId: payload.openId, appId: projectId, name, iat: typeof payload.iat === "number" ? payload.iat : 0 }, token };
  } catch {
    return null;
  }
}

export function csrfToken(sessionToken: string): string {
  return createHmac("sha256", secretKey()).update(`plus11-csrf-v1:${sessionToken}`).digest("base64url");
}

export function verifyMutation(request: Request, sessionToken: string): URL {
  const origin = validatedRequestOrigin(request);
  const supplied = request.headers.get("x-plus11-csrf");
  if (!supplied) throw new AppError("A valid request token is required. Refresh the page and try again.", 403, "csrf_required");
  const expectedBytes = Buffer.from(csrfToken(sessionToken));
  const suppliedBytes = Buffer.from(supplied);
  if (expectedBytes.length !== suppliedBytes.length || !timingSafeEqual(expectedBytes, suppliedBytes)) {
    throw new AppError("A valid request token is required. Refresh the page and try again.", 403, "csrf_invalid");
  }
  return origin;
}

function encodeState(value: OAuthState): string {
  return Buffer.from(JSON.stringify(value), "utf8").toString("base64url");
}

export function decodeOAuthState(value: string): OAuthState | null {
  try {
    const parsed = JSON.parse(Buffer.from(value, "base64url").toString("utf8")) as Partial<OAuthState>;
    if (typeof parsed.redirectUri !== "string" || typeof parsed.nonce !== "string") return null;
    const callback = new URL(parsed.redirectUri);
    if (!isAllowedPublicOrigin(callback.origin) || callback.pathname !== OAUTH_CALLBACK_PATH || callback.search || callback.hash) return null;
    if (parsed.nonce.length < 32 || parsed.nonce.length > 128) return null;
    return { redirectUri: callback.toString(), nonce: parsed.nonce };
  } catch {
    return null;
  }
}

export function startOAuth(request: Request): { authorizationUrl: string; stateCookie: string; publicOrigin: URL } {
  const requestUrl = new URL(request.url);
  const rawOrigin = requestUrl.searchParams.get("origin");
  const referer = request.headers.get("referer");
  if (!rawOrigin || !isAllowedPublicOrigin(rawOrigin)) throw new Error("Sign-in must start from an allowed Plus11 page.");
  const publicOrigin = new URL(rawOrigin);
  if (referer) {
    let refererOrigin: string;
    try { refererOrigin = new URL(referer).origin; } catch { throw new Error("Sign-in must start from an allowed Plus11 page."); }
    if (refererOrigin !== publicOrigin.origin) throw new Error("Sign-in must start from an allowed Plus11 page.");
  }

  const projectId = requiredEnv("MANUS_PROJECT_ID");
  const portal = new URL("/app-auth", requiredEnv("MANUS_OAUTH_PORTAL_URL"));
  const redirectUri = new URL(OAUTH_CALLBACK_PATH, publicOrigin).toString();
  const nonce = randomBytes(32).toString("base64url");
  const state = encodeState({ redirectUri, nonce });
  portal.searchParams.set("appId", projectId);
  portal.searchParams.set("redirectUri", redirectUri);
  portal.searchParams.set("state", state);
  portal.searchParams.set("responseType", "code");
  return { authorizationUrl: portal.toString(), stateCookie: nonce, publicOrigin };
}

export function verifyOAuthStateCookie(request: Request, state: OAuthState): boolean {
  const cookie = readCookie(request, OAUTH_STATE_COOKIE);
  if (!cookie || cookie.length !== state.nonce.length) return false;
  const left = Buffer.from(cookie);
  const right = Buffer.from(state.nonce);
  return left.length === right.length && timingSafeEqual(left, right);
}

export async function exchangeManusCode(code: string, redirectUri: string): Promise<{ openId: string; name: string }> {
  const projectId = requiredEnv("MANUS_PROJECT_ID");
  const apiBase = requiredEnv("MANUS_OAUTH_API_URL").replace(/\/+$/, "");
  const exchangeResponse = await fetch(`${apiBase}/webdev.v1.WebDevAuthPublicService/ExchangeToken`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ clientId: projectId, grantType: "authorization_code", code, redirectUri }),
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  if (!exchangeResponse.ok) throw new Error("The sign-in provider could not exchange the authorization code.");
  const exchange = await exchangeResponse.json() as { accessToken?: unknown };
  if (typeof exchange.accessToken !== "string" || !exchange.accessToken) throw new Error("The sign-in provider returned an invalid token response.");

  const userResponse = await fetch(`${apiBase}/webdev.v1.WebDevAuthPublicService/GetUserInfo`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ accessToken: exchange.accessToken }),
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  if (!userResponse.ok) throw new Error("The sign-in provider could not verify the learner identity.");
  const user = await userResponse.json() as ManusUserInfo;
  if (typeof user.openId !== "string" || !user.openId || user.openId.length > 191) throw new Error("The sign-in provider returned an invalid learner identity.");
  const name = typeof user.name === "string" && user.name.trim() ? user.name.trim().slice(0, 80) : "Learner";
  return { openId: user.openId, name };
}
