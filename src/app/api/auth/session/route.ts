import { authenticated, handleApiError, json } from "@/lib/api-server";
import { csrfToken } from "@/lib/auth";
import { ensureLearner } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return json({ user: null, csrfToken: null });
  try {
    const profile = await ensureLearner(auth.result.session.openId, auth.result.session.name);
    return json({ user: profile, csrfToken: csrfToken(auth.result.token) });
  } catch (error) {
    return handleApiError(error, "We couldn’t check your account just now. Please try again.");
  }
}
