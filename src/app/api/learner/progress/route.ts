import { authenticated, handleApiError, json } from "@/lib/api-server";
import { getProgress } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    return json(await getProgress(auth.result.session.openId));
  } catch (error) {
    return handleApiError(error, "We couldn’t load your progress just now. Please try again.");
  }
}
