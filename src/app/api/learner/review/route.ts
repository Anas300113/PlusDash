import { authenticated, handleApiError, json } from "@/lib/api-server";
import { listDueReviewCards } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    const cards = await listDueReviewCards(auth.result.session.openId);
    return json({ cards, dueCount: cards.length });
  } catch (error) {
    return handleApiError(error, "We couldn’t load your review cards just now. Please try again.");
  }
}
