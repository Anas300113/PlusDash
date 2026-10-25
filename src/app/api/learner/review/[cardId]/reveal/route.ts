import { authenticated, handleApiError, json } from "@/lib/api-server";
import { verifyMutation } from "@/lib/auth";
import { revealReviewCard } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ cardId: string }> }) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    verifyMutation(request, auth.result.token);
    const { cardId } = await context.params;
    return json(await revealReviewCard(auth.result.token, cardId));
  } catch (error) {
    return handleApiError(error, "We couldn’t reveal this answer just now. Please try again.");
  }
}
