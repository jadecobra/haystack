import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";

const UPSTREAM_TIMEOUT_MS = 15_000;
const VALID_SCREENS = new Set(["sp500-oe-yield", "sp1500-oe-yield"]);

function backendOrigin(): string {
  return (
    process.env.BACKEND_ORIGIN ||
    process.env.HAYSTACK_BACKEND_ORIGIN ||
    "http://127.0.0.1:8000"
  );
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

async function readSeed(screen: string): Promise<unknown | null> {
  const filePath = path.join(
    process.cwd(),
    "public",
    "screen",
    `${screen}.json`,
  );
  try {
    const text = await readFile(filePath, "utf8");
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function withStale(payload: unknown, note: string): unknown {
  if (typeof payload !== "object" || payload === null) return payload;
  const body = payload as Record<string, unknown>;
  const existing = typeof body.error === "string" ? body.error : null;
  return {
    ...body,
    stale: true,
    error: existing && existing !== note ? `${existing}; ${note}` : note,
  };
}

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ screen: string }> },
) {
  const { screen } = await context.params;
  if (!VALID_SCREENS.has(screen)) {
    return NextResponse.json({ error: "unknown screen" }, { status: 404 });
  }

  const url = `${backendOrigin()}/screen/${screen}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    const upstream = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (upstream.ok) {
      const body = await upstream.text();
      return new NextResponse(body, {
        status: 200,
        headers: {
          "content-type":
            upstream.headers.get("content-type") || "application/json",
        },
      });
    }
  } catch (err) {
    if (!isAbortError(err) && !(err instanceof Error)) {
      // Non-Error rejection still falls back to the disk snapshot.
    }
  } finally {
    clearTimeout(timer);
  }

  const seed = await readSeed(screen);
  if (seed) {
    return NextResponse.json(withStale(seed, "serving last-good snapshot"));
  }
  return NextResponse.json(
    { error: "screen snapshot missing", stale: true, rows: [] },
    { status: 503 },
  );
}
