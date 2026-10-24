import { json, jsonError } from "@/lib/api-server";
import { getQuestionById } from "@/lib/questions";
import { getPracticeAnswerKey } from "@/lib/question-keys";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null) as { questionId?: unknown; selectedAnswer?: unknown } | null;
  if (!body || typeof body.questionId !== "string" || typeof body.selectedAnswer !== "string") {
    return jsonError("Choose one answer before checking it.", 400, "invalid_answer");
  }

  const question = getQuestionById(body.questionId);
  const key = getPracticeAnswerKey(body.questionId);
  if (!question || !key || !question.options.some((option) => option.letter === body.selectedAnswer)) {
    return jsonError("This answer does not match the current question. Please refresh and try again.", 400, "unknown_question_or_answer");
  }

  const isCorrect = body.selectedAnswer === key.answer;
  return json({ isCorrect, explanation: isCorrect ? key.explanation : null });
}
