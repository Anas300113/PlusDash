import { authenticated, handleApiError, json, jsonError } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { createPracticeSession } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const body = await request.json().catch(() => null) as { subjectId?: unknown; topicId?: unknown; idempotencyKey?: unknown } | null;
    if (!body || typeof body.subjectId !== "string" || typeof body.topicId !== "string" || typeof body.idempotencyKey !== "string") {
      return jsonError("Choose a subject and topic to start practice.", 400, "invalid_practice_request");
    }
    return json(await createPracticeSession(auth.result.session.openId, body.subjectId, body.topicId, body.idempotencyKey), 201);
  } catch (error) {
    return handleApiError(error, "We couldn’t start practice just now. Please try again.");
  }
}
