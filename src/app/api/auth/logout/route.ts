import { SESSION_COOKIE, cookieOptions, verifyMutation } from "@/lib/auth";
import { authenticated, handleApiError, json } from "@/lib/api-server";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    const publicOrigin = verifyMutation(request, auth.result.token);
    const response = json({ signedOut: true });
    response.headers.append("Set-Cookie", `${SESSION_COOKIE}=; ${cookieOptions(publicOrigin, 0)}`);
    return response;
  } catch (error) {
    return handleApiError(error, "We couldn’t sign you out just now. Please try again.");
  }
}
