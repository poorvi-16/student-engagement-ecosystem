"use client";

import { useEffect } from "react";

/** Remembers an invite code from ?ref=CODE until the visitor signs in (the dashboard claims it). */
export function RefCapture() {
  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get("ref");
    if (ref) {
      try {
        localStorage.setItem("pp_ref", ref.slice(0, 16));
      } catch {}
    }
  }, []);
  return null;
}
