import { authenticated, handleApiError, json, jsonError } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { getLearnerProfile, updateLearnerName } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    return json({ user: await getLearnerProfile(auth.result.token) });
  } catch (error) {
    return handleApiError(error, "We couldn’t load your account just now. Please try again.");
  }
}

export async function PATCH(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const body = await request.json().catch(() => null) as { displayName?: unknown } | null;
    if (!body || typeof body.displayName !== "string") {
      return jsonError("Enter a name between 2 and 40 characters.", 400, "invalid_name");
    }
    const user = await updateLearnerName(auth.result.token, body.displayName);
    return json({ user });
  } catch (error) {
    return handleApiError(error, "We couldn’t save your name just now. Please try again.");
  }
}
