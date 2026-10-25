import { authenticated, handleApiError, json, jsonError } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { submitPracticeAnswer } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ sessionId: string }> }) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const body = await request.json().catch(() => null) as {
      questionId?: unknown; selectedAnswer?: unknown; questionIndex?: unknown;
      idempotencyKey?: unknown; timeTakenMs?: unknown; hintUsed?: unknown; action?: unknown;
    } | null;
    if (!body || typeof body.questionId !== "string" || typeof body.selectedAnswer !== "string"
        || typeof body.questionIndex !== "number" || !Number.isInteger(body.questionIndex)
        || typeof body.idempotencyKey !== "string" || !/^[0-9a-f-]{36}$/i.test(body.idempotencyKey)
        || (body.timeTakenMs !== undefined && (typeof body.timeTakenMs !== "number" || !Number.isInteger(body.timeTakenMs) || body.timeTakenMs < 0 || body.timeTakenMs > 7_200_000))
        || (body.hintUsed !== undefined && typeof body.hintUsed !== "boolean")
        || (body.action !== undefined && body.action !== "answer" && body.action !== "retry")) {
      return jsonError("Choose one answer before checking it.", 400, "invalid_answer");
    }
    const { sessionId } = await context.params;
    const result = await submitPracticeAnswer(auth.result.token, {
      sessionId,
      questionId: body.questionId,
      selectedAnswer: body.selectedAnswer,
      questionIndex: body.questionIndex,
      idempotencyKey: body.idempotencyKey,
      timeTakenMs: typeof body.timeTakenMs === "number" ? body.timeTakenMs : 0,
      hintUsed: body.hintUsed === true,
      action: body.action === "retry" ? "retry" : "answer",
    });
    return json(result);
  } catch (error) {
    return handleApiError(error, "We couldn’t save your answer just now. Please try again.");
  }
}
