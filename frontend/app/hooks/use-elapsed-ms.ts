"use client";

import { useEffect, useState } from "react";

export function useElapsedMs(active: boolean): number {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (!active) return;
    const startedAt = Date.now();
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 100);
    return () => {
      window.clearInterval(id);
      setElapsedMs(0);
    };
  }, [active]);

  return active ? elapsedMs : 0;
}
