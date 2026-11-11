import type { ReactNode } from "react";

/** Pannello HUD: titolo MAIUSCOLO // sottotitoli separati da · , etichetta di stato a destra. */
export function Panel({ title, parts = [], tag, tagColor = "#3DD6FF", className = "", children, bodyClass = "p-3" }: {
  title: string; parts?: string[]; tag?: string; tagColor?: string; className?: string; children: ReactNode;
  bodyClass?: string;
}) {
  return (
    <section className={`panel flex flex-col min-w-0 ${className}`} aria-label={title}>
      <header className="flex items-center gap-3 border-b border-edge px-3 py-2">
        <span className="text-cyan" aria-hidden>◆</span>
        <h2 className="label !text-ink !text-[10.5px] font-medium whitespace-nowrap">{title}</h2>
        {parts.length > 0 && (
          <span className="label truncate">// {parts.join(" · ")}</span>
        )}
        {tag && (
          <span className="tag ml-auto whitespace-nowrap" style={{ color: tagColor, borderColor: tagColor }}>{tag}</span>
        )}
      </header>
      <div className={`flex-1 min-h-0 ${bodyClass}`}>{children}</div>
    </section>
  );
}

export function Sparkline({ values, color = "#3DD6FF", height = 26 }: { values: (number | null)[]; color?: string; height?: number }) {
  const v = values.filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  if (v.length < 2) return <div className="text-mute" style={{ height }}>—</div>;
  const lo = Math.min(...v), hi = Math.max(...v), w = 120;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${height - 2 - ((x - lo) / (hi - lo || 1)) * (height - 4)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }} aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" style={{ filter: `drop-shadow(0 0 3px ${color})` }} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
