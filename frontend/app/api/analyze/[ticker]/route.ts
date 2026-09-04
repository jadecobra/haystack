import { NextRequest, NextResponse } from "next/server";

function backendOrigin(): string {
  return (
    process.env.BACKEND_ORIGIN ||
    process.env.HAYSTACK_BACKEND_ORIGIN ||
    "http://127.0.0.1:8000"
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
  try {
    const upstream = await fetch(url, { cache: "no-store" });
    const body = await upstream.text();
    return new NextResponse(body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") || "application/json",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "backend unreachable";
    return NextResponse.json(
      { error: "backend unreachable", detail: message, backend: backendOrigin() },
      { status: 502 },
    );
  }
}
