import { authenticated, handleApiError, json, jsonError } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { recordReviewOutcome } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ cardId: string }> }) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const body = await request.json().catch(() => null) as { outcome?: unknown; eventId?: unknown } | null;
    if (!body || (body.outcome !== "got-it" && body.outcome !== "again") || typeof body.eventId !== "string") {
      return jsonError("Choose whether you got it or need another look.", 400, "invalid_review_outcome");
    }
    const { cardId } = await context.params;
    return json(await recordReviewOutcome(auth.result.session.openId, cardId, body.outcome, body.eventId));
  } catch (error) {
    return handleApiError(error, "We couldn’t save this review just now. Please try again.");
  }
}
