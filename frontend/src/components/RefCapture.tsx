"use client";

import { useEffect } from "react";

/**
 * Remembers an invite code (?ref=CODE) and campaign tags (?utm_source=…) until the visitor signs in.
 * The dashboard claims the invite and reports the campaign once, so the admin funnel can split signups by source.
 */
export function RefCapture() {
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const ref = q.get("ref");
    const source = q.get("utm_source");
    try {
      if (ref) localStorage.setItem("pp_ref", ref.slice(0, 16));
      if (source) {
        localStorage.setItem(
          "pp_utm",
          JSON.stringify({
            source: source.slice(0, 40),
            medium: (q.get("utm_medium") ?? "").slice(0, 40),
            campaign: (q.get("utm_campaign") ?? "").slice(0, 80),
          }),
        );
      }
    } catch {}
  }, []);
  return null;
}
