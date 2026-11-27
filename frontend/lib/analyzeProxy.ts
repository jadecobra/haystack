export const UPSTREAM_TIMEOUT_MS = 20_000;
export const MAX_UPSTREAM_ATTEMPTS = 2;

export type AnalyzeProxyResult =
  | { kind: "upstream"; status: number; body: string; contentType: string }
  | { kind: "timeout" }
  | { kind: "unreachable"; detail: string };

export interface AnalyzeProxyOptions {
  fetchFn?: typeof fetch;
  timeoutMs?: number;
  maxAttempts?: number;
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException &&
      (err.name === "AbortError" || err.name === "TimeoutError")) ||
    (err instanceof Error &&
      (err.name === "AbortError" || err.name === "TimeoutError"))
  );
}

export async function fetchAnalyzeWithRetry(
  url: string,
  options: AnalyzeProxyOptions = {},
): Promise<AnalyzeProxyResult> {
  const fetchFn = options.fetchFn ?? fetch;
  const timeoutMs = options.timeoutMs ?? UPSTREAM_TIMEOUT_MS;
  const maxAttempts = Math.max(1, options.maxAttempts ?? MAX_UPSTREAM_ATTEMPTS);

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const upstream = await fetchFn(url, {
        cache: "no-store",
        signal: AbortSignal.timeout(timeoutMs),
      });
      const body = await upstream.text();
      return {
        kind: "upstream",
        status: upstream.status,
        body,
        contentType:
          upstream.headers.get("content-type") || "application/json",
      };
    } catch (err) {
      if (isAbortError(err)) {
        if (attempt < maxAttempts) {
          continue;
        }
        return { kind: "timeout" };
      }
      const message =
        err instanceof Error ? err.message : "backend unreachable";
      return { kind: "unreachable", detail: message };
    }
  }

  return { kind: "timeout" };
}
