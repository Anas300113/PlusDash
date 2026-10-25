import { authenticated, handleApiError, json } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { abandonPracticeSession } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ sessionId: string }> }) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const { sessionId } = await context.params;
    return json(await abandonPracticeSession(auth.result.token, sessionId));
  } catch (error) {
    return handleApiError(error, "We couldn’t leave your session just now. Please try again.");
  }
}
