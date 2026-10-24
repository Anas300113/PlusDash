import "server-only";

import { NextResponse } from "next/server";
import { getLearnerSession } from "@/lib/auth";
import { AppError } from "@/lib/errors";

export function json(data: unknown, status = 200): NextResponse {
  const response = NextResponse.json(data, { status });
  response.headers.set("Cache-Control", "no-store, max-age=0");
  response.headers.set("Pragma", "no-cache");
  return response;
}

export function jsonError(message: string, status: number, code: string): NextResponse {
  return json({ error: message, code }, status);
}

export async function authenticated(request: Request) {
  const result = await getLearnerSession(request);
  if (!result) return { response: jsonError("Please sign in to save your learning.", 401, "unauthenticated") };
  return { result };
}

export function handleApiError(error: unknown, fallback = "We couldn’t complete that just now. Please try again."): NextResponse {
  if (error instanceof AppError) return jsonError(error.message, error.status, error.code);
  return jsonError(fallback, 500, "server_error");
}
