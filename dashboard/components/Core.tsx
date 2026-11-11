"use client";
import { useLayoutEffect, useRef, useState } from "react";
import { Panel } from "./Panel";
import { Sphere } from "./Sphere";
import { OBS, Observable } from "./Panels";
import type { State, Verdict } from "@/lib/live";
import { num, VERDICT_COLOR } from "@/lib/fmt";

const TAG: Record<string, string> = { BUY: "BUY", SELL: "SHORT", EXIT: "EXIT", HOLD: "HOLD", SKIP: "SKIP", VETO: "VETO" };

function VerdictCard({ v }: { v: Verdict }) {
  const c = VERDICT_COLOR[v.verdict] ?? "#6B7A90";
  return (
    <article data-verdict={v.symbol} className="grid grid-cols-[1fr_auto] gap-x-2 border px-2.5 py-1.5"
      style={{ borderColor: `${c}55`, background: `linear-gradient(90deg, ${c}14, transparent 70%)` }}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="tag !text-[9px]" style={{ color: c, borderColor: c }}>{TAG[v.verdict] ?? v.verdict}</span>
          <b className="text-[12px] text-ink">{v.symbol}</b>
          <span className="label !text-[9px] truncate">{v.strategy} · {num(v.price)}</span>
        </div>
        <p className="mt-0.5 truncate text-[10.5px] text-mute" title={v.veto ?? v.reason}>{v.veto ?? v.reason}</p>
      </div>
      <div className="self-center text-[24px] font-light leading-none" style={{ color: c, textShadow: `0 0 12px ${c}88` }}>
        {Math.round(v.confidence)}
      </div>
    </article>
  );
}

type Link = { d: string; color: string };

export function Core({ s, pulse }: { s: State; pulse: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const [links, setLinks] = useState<Link[]>([]);
  const verdicts = (s.verdicts ?? []).slice(0, 15);
  const shown = verdicts.slice(0, 9);
  const regime = s.observables?.regime?.value as string | undefined;

  // Linee curve: dalle carte dei verdetti alla sfera, e dalla sfera alle osservabili
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const draw = () => {
      if (window.innerWidth < 1100) { setLinks([]); return; }
      const b = el.getBoundingClientRect();
      const sphere = el.querySelector("[data-sphere]")?.getBoundingClientRect();
      if (!sphere) return;
      const cx = sphere.left + sphere.width / 2 - b.left, cy = sphere.top + sphere.height / 2 - b.top;
      const r = Math.min(sphere.width, sphere.height) * 0.3;
      const out: Link[] = [];
      // punto sul bordo della sfera, dal lato giusto, alla stessa altezza relativa della carta
      const rim = (y: number, side: -1 | 1) => {
        const dy = Math.max(-r * 0.9, Math.min(r * 0.9, (y - cy) * 0.6));
        return [cx + side * Math.sqrt(r * r - dy * dy), cy + dy];
      };
      el.querySelectorAll<HTMLElement>("[data-verdict]").forEach((card, i) => {
        const cr = card.getBoundingClientRect();
        const x1 = cr.right - b.left, y1 = cr.top + cr.height / 2 - b.top;
        const [x2, y2] = rim(y1, -1);
        out.push({ d: `M${x1},${y1} C${x1 + 80},${y1} ${x2 - 90},${y2} ${x2},${y2}`, color: VERDICT_COLOR[shown[i]?.verdict] ?? "#6B7A90" });
      });
      el.querySelectorAll<HTMLElement>("[data-obs]").forEach((card, i) => {
        const cr = card.getBoundingClientRect();
        const x2 = cr.left - b.left, y2 = cr.top + cr.height / 2 - b.top;
        const [x1, y1] = rim(y2, 1);
        out.push({ d: `M${x1},${y1} C${x1 + 90},${y1} ${x2 - 80},${y2} ${x2},${y2}`, color: OBS[i]?.color ?? "#3DD6FF" });
      });
      setLinks(out);
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [shown.map((v) => v.symbol + v.verdict).join()]); // eslint-disable-line react-hooks/exhaustive-deps

  const counts = verdicts.reduce<Record<string, number>>((m, v) => ({ ...m, [v.verdict]: (m[v.verdict] ?? 0) + 1 }), {});
  return (
    <Panel title="The Core" parts={["Signals", "Regime", "Verdict"]} className={pulse ? "flash" : ""}
      tag={counts.VETO ? `${counts.VETO} VETOED` : `${verdicts.length} SYMBOLS`} tagColor={counts.VETO ? "#FF4D5E" : "#3DD6FF"}
      bodyClass="p-0">
      <div ref={box} className="relative grid min-h-[520px] grid-cols-1 gap-3 p-3 min-[1100px]:grid-cols-[330px_1fr_270px]">
        <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
          {links.map((l, i) => (
            <path key={i} d={l.d} fill="none" stroke={l.color} strokeWidth="1.2" opacity="0.55"
              style={{ filter: `drop-shadow(0 0 3px ${l.color})` }} />
          ))}
        </svg>
        <div className="relative z-10 flex flex-col gap-1.5">
          <div className="label mb-1 flex justify-between"><span>Verdict stack</span><span>score 0-100</span></div>
          {shown.length ? shown.map((v) => <VerdictCard key={v.symbol} v={v} />)
            : <p className="text-mute">Nessuna decisione ancora: il riflesso valuta ogni 15 minuti a mercato aperto.</p>}
        </div>
        <div data-sphere className="relative min-h-[420px]">
          <Sphere verdicts={verdicts} regime={regime} pulse={pulse} />
          <div className="pointer-events-none absolute bottom-2 left-0 right-0 flex justify-center gap-3 text-[10px]">
            {Object.entries(counts).map(([k, n]) => (
              <span key={k} style={{ color: VERDICT_COLOR[k] }}>{k} {n}</span>
            ))}
          </div>
        </div>
        <div className="relative z-10 flex flex-col gap-1.5">
          <div className="label mb-1">Observables</div>
          {OBS.map((o) => <Observable key={o.key} s={s} o={o} />)}
        </div>
      </div>
    </Panel>
  );
}
