import { NextResponse } from "next/server";
import { OAUTH_STATE_COOKIE, cookieOptions, isAllowedPublicOrigin, startOAuth } from "@/lib/auth";
import { jsonError } from "@/lib/api-server";

export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const started = startOAuth(request);
    const response = NextResponse.redirect(started.authorizationUrl, { status: 302 });
    response.headers.append("Set-Cookie", `${OAUTH_STATE_COOKIE}=${encodeURIComponent(started.stateCookie)}; ${cookieOptions(started.publicOrigin, 600)}`);
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    const origin = new URL(request.url).searchParams.get("origin");
    if (origin && isAllowedPublicOrigin(origin)) {
      return NextResponse.redirect(new URL("/account?auth=error", origin), { status: 303 });
    }
    return jsonError("Sign-in couldn’t start from this page. Return to Plus11 and try again.", 400, "auth_start_failed");
  }
}
