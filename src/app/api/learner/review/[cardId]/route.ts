import { authenticated, handleApiError, json, jsonError } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { updateReviewCard } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ cardId: string }> }) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const body = await request.json().catch(() => null) as { outcome?: unknown; eventId?: unknown } | null;
    if (!body || (body.outcome !== "got-it" && body.outcome !== "again") || typeof body.eventId !== "string") {
      return jsonError("Choose how the review went before continuing.", 400, "invalid_review");
    }
    const { cardId } = await context.params;
    return json(await updateReviewCard(auth.result.token, cardId, body.outcome, body.eventId));
  } catch (error) {
    return handleApiError(error, "We couldn’t save this review just now. Please try again.");
  }
}
