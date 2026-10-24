import { NextResponse } from "next/server";
import { OAUTH_STATE_COOKIE, SESSION_COOKIE, cookieOptions, decodeOAuthState, exchangeManusCode, signLearnerSession, verifyOAuthStateCookie } from "@/lib/auth";
import { ensureLearner } from "@/lib/learner-service";

export const runtime = "nodejs";

function accountRedirect(origin: string, state: string) {
  const destination = new URL("/account", origin);
  destination.searchParams.set("auth", state);
  return NextResponse.redirect(destination, { status: 303 });
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const state = decodeOAuthState(url.searchParams.get("state") ?? "");
  const publicOrigin = state ? new URL(state.redirectUri).origin : null;
  if (!state || !publicOrigin || !verifyOAuthStateCookie(request, state)) {
    return new Response("Sign-in could not be verified. Return to Plus11 and try again.", {
      status: 400,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }

  const code = url.searchParams.get("code");
  if (!code || code.length > 4096 || url.searchParams.has("error")) {
    const response = accountRedirect(publicOrigin, "error");
    response.headers.append("Set-Cookie", `${OAUTH_STATE_COOKIE}=; ${cookieOptions(new URL(publicOrigin), 0)}`);
    return response;
  }

  try {
    const user = await exchangeManusCode(code, state.redirectUri);
    const profile = await ensureLearner(user.openId, user.name);
    const sessionToken = await signLearnerSession({ openId: user.openId, name: profile.displayName });
    const response = accountRedirect(publicOrigin, "success");
    response.headers.append("Set-Cookie", `${SESSION_COOKIE}=${encodeURIComponent(sessionToken)}; ${cookieOptions(new URL(publicOrigin))}`);
    response.headers.append("Set-Cookie", `${OAUTH_STATE_COOKIE}=; ${cookieOptions(new URL(publicOrigin), 0)}`);
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    const response = accountRedirect(publicOrigin, "error");
    response.headers.append("Set-Cookie", `${OAUTH_STATE_COOKIE}=; ${cookieOptions(new URL(publicOrigin), 0)}`);
    return response;
  }
}
