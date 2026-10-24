import { authenticated, handleApiError, json } from "@/lib/api-server";
import { getDashboard } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    return json(await getDashboard(auth.result.session.openId));
  } catch (error) {
    return handleApiError(error, "We couldn’t load your learning today. Please try again.");
  }
}
