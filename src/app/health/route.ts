import { getPool } from "@/lib/db";
import type { RowDataPacket } from "mysql2/promise";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [rows] = await getPool().execute<RowDataPacket[]>("SELECT migration_name FROM plus11_schema_migrations WHERE migration_name = '001_plus11_learning' LIMIT 1");
    if (!rows[0]) return Response.json({ ok: false }, { status: 503, headers: { "cache-control": "no-store" } });
    return Response.json({ ok: true }, { headers: { "cache-control": "no-store" } });
  } catch {
    return Response.json({ ok: false }, { status: 503, headers: { "cache-control": "no-store" } });
  }
}
