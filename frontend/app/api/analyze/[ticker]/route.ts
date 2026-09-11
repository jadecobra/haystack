import { NextRequest, NextResponse } from "next/server";

const UPSTREAM_TIMEOUT_MS = 20_000;

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

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ ticker: string }> },
) {
  const { ticker } = await context.params;
  const symbol = (ticker || "").toUpperCase().trim();
  if (!symbol) {
    return NextResponse.json({ error: "ticker required" }, { status: 400 });
  }

  const url = `${backendOrigin()}/analyze/${encodeURIComponent(symbol)}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    const upstream = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });
    const body = await upstream.text();
    return new NextResponse(body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") || "application/json",
      },
    });
  } catch (err) {
    if (isAbortError(err)) {
      return NextResponse.json(
        {
          error: "upstream timeout",
          detail: "This is taking too long. Try again.",
        },
        { status: 504 },
      );
    }
    const message = err instanceof Error ? err.message : "backend unreachable";
    return NextResponse.json(
      { error: "backend unreachable", detail: message },
      { status: 502 },
    );
  } finally {
    clearTimeout(timer);
  }
}
