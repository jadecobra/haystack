/** GA4 for longmuch.com only. Measurement ID is Jacob's property. */

export const GA_MEASUREMENT_ID = "G-RBK1ZGN2HX";

/** Production hostname. Previews, *.vercel.app, and localhost stay untagged. */
export const GA_HOSTNAME = "longmuch.com";

export function shouldLoadGa4(hostname: string): boolean {
  return hostname === GA_HOSTNAME;
}

export function gtagScriptSrc(measurementId: string = GA_MEASUREMENT_ID): string {
  return `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
}

/** SPA navigations. The initial view is the gtag config page_view. */
export function pageViewArgs(pagePath: string): ["event", "page_view", { page_path: string; send_to: string }] {
  return [
    "event",
    "page_view",
    { page_path: pagePath, send_to: GA_MEASUREMENT_ID },
  ];
}

export const VERCEL_APP_HOST = "longmuch.vercel.app";

/** 308 the production *.vercel.app alias to the apex. Preview hosts are unchanged. */
export function vercelAppRedirect() {
  return {
    source: "/:path*",
    has: [{ type: "host" as const, value: VERCEL_APP_HOST }],
    destination: "https://longmuch.com/:path*",
    permanent: true,
  };
}
