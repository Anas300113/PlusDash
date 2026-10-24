import { authenticated, handleApiError, json, jsonError } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { submitPracticeAnswer } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ sessionId: string }> }) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const body = await request.json().catch(() => null) as { questionId?: unknown; selectedAnswer?: unknown; questionIndex?: unknown; idempotencyKey?: unknown } | null;
    if (!body || typeof body.questionId !== "string" || typeof body.selectedAnswer !== "string" || typeof body.questionIndex !== "number" || typeof body.idempotencyKey !== "string") {
      return jsonError("Choose one answer before checking it.", 400, "invalid_answer");
    }
    const { sessionId } = await context.params;
    const result = await submitPracticeAnswer(auth.result.session.openId, {
      sessionId,
      questionId: body.questionId,
      selectedAnswer: body.selectedAnswer,
      questionIndex: body.questionIndex,
      idempotencyKey: body.idempotencyKey,
    });
    return json(result);
  } catch (error) {
    return handleApiError(error, "We couldn’t save your answer just now. Please try again.");
  }
}
