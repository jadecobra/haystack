"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import {
  GA_MEASUREMENT_ID,
  gtagScriptSrc,
  pageViewArgs,
  shouldLoadGa4,
} from "../../lib/ga4";

type Gtag = (...args: unknown[]) => void;

/** Last path we already counted. Survives Strict Mode remounts. */
let lastTrackedPath: string | null = null;

function readGtag(): Gtag | undefined {
  const fn = (window as Window & { gtag?: Gtag }).gtag;
  return typeof fn === "function" ? fn : undefined;
}

function bootGa4(): void {
  if (document.getElementById("ga4-init")) return;
  const loader = document.createElement("script");
  loader.src = gtagScriptSrc();
  loader.async = true;
  document.head.appendChild(loader);
  const inline = document.createElement("script");
  inline.id = "ga4-init";
  inline.text =
    `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag('js',new Date());gtag('config','${GA_MEASUREMENT_ID}');`;
  document.head.appendChild(inline);
}

export function GoogleAnalytics() {
  const pathname = usePathname();

  useEffect(() => {
    if (!shouldLoadGa4(window.location.hostname)) return;
    if (!document.getElementById("ga4-init")) {
      bootGa4();
      lastTrackedPath = pathname;
      return;
    }
    if (lastTrackedPath === pathname) return;
    lastTrackedPath = pathname;
    const gtag = readGtag();
    if (!gtag) return;
    const [command, name, params] = pageViewArgs(pathname);
    gtag(command, name, params);
  }, [pathname]);

  return null;
}
