export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const origin = process.env.PLUS_API_BASE_URL ?? "http://127.0.0.1:8001";
  try {
    const response = await fetch(`${origin}/api/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) {
      return Response.json(
        { ok: false, service: "plus11" },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }
    return Response.json(
      { ok: true, service: "plus11" },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return Response.json(
      { ok: false, service: "plus11" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}
