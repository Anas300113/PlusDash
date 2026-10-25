import { authenticated, handleApiError, json } from "@/lib/api-server";
import { getPracticeSession } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request, context: { params: Promise<{ sessionId: string }> }) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    const { sessionId } = await context.params;
    return json(await getPracticeSession(auth.result.token, sessionId));
  } catch (error) {
    return handleApiError(error, "We couldn’t resume your practice session. Please try again.");
  }
}
