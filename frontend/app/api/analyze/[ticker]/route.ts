import { NextRequest, NextResponse } from "next/server";
import { fetchAnalyzeWithRetry } from "@/lib/analyzeProxy";

export const maxDuration = 60;

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
  const result = await fetchAnalyzeWithRetry(url);

  if (result.kind === "upstream") {
    return new NextResponse(result.body, {
      status: result.status,
      headers: { "content-type": result.contentType },
    });
  }

  if (result.kind === "timeout") {
    return NextResponse.json(
      {
        error: "upstream timeout",
        detail: "This is taking too long. Try again.",
      },
      { status: 504 },
    );
  }

  return NextResponse.json(
    { error: "backend unreachable", detail: result.detail },
    { status: 502 },
  );
}
