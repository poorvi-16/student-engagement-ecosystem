import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "PathPilot study card";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Social preview (WhatsApp/LinkedIn) for a public study card. */
export default async function Image({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  let card: { first_name: string; target: { field: string | null; countries: string[]; intake: string | null }; level: { name: string } } | null = null;
  try {
    const r = await fetch(`${API}/public/card/${code}`, { next: { revalidate: 300 } });
    if (r.ok) card = await r.json();
  } catch {}
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", padding: 80, background: "linear-gradient(135deg,#4f46e5,#6d28d9)", color: "white", fontSize: 40 }}>
        <div style={{ fontSize: 28, opacity: 0.8, letterSpacing: 6 }}>PATHPILOT · STUDY CARD</div>
        <div style={{ fontSize: 88, fontWeight: 700, marginTop: 20 }}>{card?.first_name ?? "Plan your studies abroad"}</div>
        {card && (
          <div style={{ marginTop: 16, opacity: 0.9 }}>
            {card.target.field ?? ""} · {card.target.countries.join(" · ")} {card.target.intake ? `· ${card.target.intake}` : ""}
          </div>
        )}
        <div style={{ marginTop: 40, fontSize: 30, opacity: 0.85 }}>{card ? `Level: ${card.level.name}` : "AI copilot for higher studies"}</div>
      </div>
    ),
    size,
  );
}
