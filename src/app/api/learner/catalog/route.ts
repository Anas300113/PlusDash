import { authenticated, handleApiError, json } from "@/lib/api-server";
import { getCatalog } from "@/lib/learner-service";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const auth = await authenticated(request);
  if ("response" in auth) return auth.response;
  try {
    return json(await getCatalog(auth.result.token));
  } catch (error) {
    return handleApiError(error, "We couldn’t load the reviewed question bank. Please try again.");
  }
}
