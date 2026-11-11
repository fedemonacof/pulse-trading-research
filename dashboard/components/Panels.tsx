"use client";
import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi, LineStyle, type UTCTimestamp } from "lightweight-charts";
import { Panel, Sparkline } from "./Panel";
import type { State } from "@/lib/live";
import { num, pct, sUsd, usd, upct, tone, hhmm, REGIME_COLOR, REGIME_LABEL, isNum } from "@/lib/fmt";
import { useTween } from "@/lib/anim";

const CHART_BASE = {
  autoSize: true,
  layout: { background: { color: "transparent" }, textColor: "#6B7A90", fontFamily: "var(--font-jetbrains)", fontSize: 10 },
  grid: { vertLines: { color: "rgba(28,36,48,.6)" }, horzLines: { color: "rgba(28,36,48,.6)" } },
  rightPriceScale: { borderColor: "#1C2430" },
  timeScale: { borderColor: "#1C2430", fixLeftEdge: true, fixRightEdge: true },
  crosshair: { vertLine: { labelBackgroundColor: "#1C2430" }, horzLine: { labelBackgroundColor: "#1C2430" } },
  handleScroll: false, handleScale: false,
} as const;

// ------------------------------------------------------------ STATE: il grande P&L di oggi
export function StatePanel({ s }: { s: State }) {
  const a = s.account ?? {};
  const pnl = useTween(a.day_pnl ?? null);
  const eq = useTween(a.equity ?? null);
  const regime = s.observables?.regime?.value as string | undefined;
  const up = (a.day_pnl ?? 0) >= 0;
  return (
    <Panel title="State" parts={["P&L", "Equity", a.core_enabled ? "Core + satellite" : "Regime"]}
      tag={s.halted ? "KILL SWITCH" : (s as { satellite_halted?: boolean }).satellite_halted ? "SATELLITE STOPPED"
        : s.session_paused ? "SATELLITE PAUSED" : "LIVE"}
      tagColor={s.halted || s.session_paused || (s as { satellite_halted?: boolean }).satellite_halted ? "#FF4D5E" : "#3DFF8F"}>
      <div className="label">Today P&amp;L</div>
      <div className={`mt-1 text-[clamp(40px,5vw,64px)] font-light leading-none tracking-tight ${up ? "text-gain glow-gain" : "text-loss glow-loss"}`}>
        {sUsd(pnl, 2)}
      </div>
      <div className={`mt-1 text-[13px] ${tone(a.day_ret)}`}>{pct(a.day_ret)} <span className="text-mute">vs ieri</span></div>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-edge pt-3">
        {([
          ["Equity", usd(eq, 2), "text-ink"],
          ["Total", `${pct(a.total_ret)}`, tone(a.total_ret)],
          ["SPY same period", pct(a.spy_ret), tone(a.spy_ret)],
          ["Realized", sUsd(a.realized), tone(a.realized)],
          ["Drawdown", pct(a.drawdown), "text-loss"],
          ["Exposure", upct(a.gross), "text-cyan"],
          ...(a.core_enabled ? [
            [`Core ${s.account?.core_symbol ?? "SPY"}${s.core_signal === false ? " · CASH (MA200)" : ""}`,
              upct(a.core_weight), s.core_signal === false ? "text-amber" : "text-violet"],
            s.satellite_mode === "shadow"
              ? ["Satellite · shadow", `${s.shadow_trades ?? 0} trade · ${sUsd(s.shadow_pnl)}`, tone(s.shadow_pnl)]
              : ["Satellite", `${upct(a.satellite_weight)} · ${sUsd(a.satellite_pnl)}`, tone(a.satellite_pnl)],
          ] : []),
        ] as string[][]).map(([k, v, c]) => (
          <div key={k}><dt className="label">{k}</dt><dd className={`mt-0.5 text-[15px] ${c}`}>{v}</dd></div>
        ))}
      </dl>
      <div className="mt-4 border-t border-edge pt-3">
        <div className="label">Regime</div>
        <div className="mt-1 text-[16px] font-bold tracking-[0.12em]" style={{ color: REGIME_COLOR[regime ?? ""] ?? "#6B7A90" }}>
          {REGIME_LABEL[regime ?? ""] ?? "—"}
        </div>
        <p className="mt-1 text-[11px] leading-snug text-mute">{s.observables?.regime?.reason ?? "—"}</p>
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------ LIFE OF A DECISION
const TAG_COLOR: Record<string, string> = {
  SIGNAL: "#3DD6FF", INPUT: "#9B7BFF", REASON: "#D7E0EA", RISK: "#3DFF8F", BRACKET: "#FFB547",
  FILL: "#3DFF8F", EXIT: "#3DD6FF", OPEN: "#6B7A90", VETOED: "#FF4D5E", REJECTED: "#FF4D5E",
};
export function LifeOfDecision({ s }: { s: State }) {
  const life = s.life ?? [];
  const sym = life[0]?.text.split(" ")[0];
  return (
    <Panel title="Life of a decision" parts={["Signal", "Risk", "Fill"]} tag={sym ? `TRACE ${sym}` : "NO TRADES"} tagColor="#FFB547">
      <ol className="space-y-1 text-[11px] leading-snug">
        {life.length ? life.map((l, i) => (
          <li key={i} className="grid grid-cols-[62px_64px_1fr] gap-2">
            <span className="text-mute">{hhmm(l.ts)}</span>
            <span style={{ color: TAG_COLOR[l.tag] ?? "#D7E0EA" }}>[{l.tag}]</span>
            <span className={`text-ink/90 ${i === life.length - 1 ? "cursor" : ""}`}>{l.text}</span>
          </li>
        )) : <li className="text-mute cursor">in attesa della prima entrata</li>}
      </ol>
    </Panel>
  );
}

// ------------------------------------------------------------ WHERE IT LANDS
export function WhereItLands({ s }: { s: State }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const L = s.landing;
  useEffect(() => {
    if (!el.current) return;
    chart.current = createChart(el.current, CHART_BASE);
    series.current = chart.current.addCandlestickSeries({
      upColor: "#3DFF8F", downColor: "#FF4D5E", borderVisible: false, wickUpColor: "#3DFF8F", wickDownColor: "#FF4D5E",
    });
    return () => chart.current?.remove();
  }, []);
  useEffect(() => {
    const se = series.current;
    if (!se || !L) return;
    se.setData(L.bars.map(([d, o, h, l, c]) => ({ time: d, open: o, high: h, low: l, close: c })));
    (se as unknown as { _lines?: unknown[] })._lines?.forEach((p) => se.removePriceLine(p as never));
    const lines = [
      isNum(L.entry) && se.createPriceLine({ price: L.entry, color: "#D7E0EA", lineStyle: LineStyle.Dashed, lineWidth: 1, title: "ENTRY" }),
      isNum(L.stop) && se.createPriceLine({ price: L.stop, color: "#FF4D5E", lineStyle: LineStyle.Solid, lineWidth: 1, title: "STOP" }),
      isNum(L.take_profit) && se.createPriceLine({ price: L.take_profit, color: "#3DFF8F", lineStyle: LineStyle.Solid, lineWidth: 1, title: "TARGET" }),
    ].filter(Boolean);
    (se as unknown as { _lines?: unknown[] })._lines = lines;
    chart.current?.timeScale().fitContent();
  }, [L]);
  return (
    <Panel title="Where it lands" parts={[L?.symbol ?? "—", "Entry · Stop · Target"]} tag={L ? L.side.toUpperCase() : "—"}
      tagColor={L?.side === "short" ? "#FF4D5E" : "#3DFF8F"} bodyClass="p-2">
      <div ref={el} className="h-[190px] w-full" />
      <div className="mt-1 grid grid-cols-3 gap-2 px-1 text-[11px]">
        <div><span className="label">Entry</span> <span className="text-ink">{num(L?.entry)}</span></div>
        <div><span className="label">Stop</span> <span className="text-loss">{num(L?.stop)}</span></div>
        <div><span className="label">Target</span> <span className="text-gain">{num(L?.take_profit)}</span></div>
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------ EQUITY VS SPY + DRAWDOWN
export function EquityPanel({ s }: { s: State }) {
  const el = useRef<HTMLDivElement>(null);
  const dd = useRef<HTMLDivElement>(null);
  const refs = useRef<{ c?: IChartApi; d?: IChartApi; eq?: ISeriesApi<"Area">; spy?: ISeriesApi<"Line">; dd?: ISeriesApi<"Area"> }>({});
  useEffect(() => {
    if (!el.current || !dd.current) return;
    const c = createChart(el.current, { ...CHART_BASE, timeScale: { ...CHART_BASE.timeScale, timeVisible: true } });
    const d = createChart(dd.current, { ...CHART_BASE, timeScale: { ...CHART_BASE.timeScale, visible: false } });
    refs.current = {
      c, d,
      eq: c.addAreaSeries({ lineColor: "#3DFF8F", topColor: "rgba(61,255,143,.25)", bottomColor: "rgba(61,255,143,0)", lineWidth: 2, priceLineVisible: false }),
      spy: c.addLineSeries({ color: "#9B7BFF", lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false }),
      dd: d.addAreaSeries({ lineColor: "#FF4D5E", topColor: "rgba(255,77,94,0)", bottomColor: "rgba(255,77,94,.35)", lineWidth: 1, priceLineVisible: false,
        priceFormat: { type: "percent" } }),
    };
    return () => { c.remove(); d.remove(); };
  }, []);
  useEffect(() => {
    const r = refs.current;
    if (!r.eq || !s.equity) return;
    const t = (p: { time: number; value: number }) => ({ time: p.time as UTCTimestamp, value: p.value });
    r.eq.setData(s.equity.map(t));
    r.spy?.setData((s.spy ?? []).map(t));
    r.dd?.setData((s.drawdown ?? []).map((p) => ({ time: p.time as UTCTimestamp, value: p.value * 100 })));
    r.c?.timeScale().fitContent();
    r.d?.timeScale().fitContent();
  }, [s.equity, s.spy, s.drawdown]);
  const a = s.account ?? {};
  return (
    <Panel title="Equity vs SPY" parts={["Same start capital", "Drawdown"]} tag={isNum(a.total_ret) && isNum(a.spy_ret)
      ? (a.total_ret! >= a.spy_ret! ? "AHEAD OF SPY" : "BEHIND SPY") : "—"}
      tagColor={(a.total_ret ?? 0) >= (a.spy_ret ?? 0) ? "#3DFF8F" : "#FF4D5E"} bodyClass="p-2">
      <div className="flex gap-4 px-1 pb-1 text-[11px]">
        <span><span className="text-gain">━</span> PULSE {pct(a.total_ret)}</span>
        <span><span className="text-violet">┄</span> SPY {pct(a.spy_ret)}</span>
        <span className="ml-auto"><span className="text-loss">▁</span> MAX DD {pct(a.max_drawdown)}</span>
      </div>
      <div ref={el} className="h-[180px] w-full" />
      <div ref={dd} className="h-[60px] w-full" />
    </Panel>
  );
}

// ------------------------------------------------------------ OBSERVABLES (colonna destra del core)
export const OBS = [
  { key: "volatility", label: "Volatility", sub: "SPY 20d annualized", fmt: (v: number) => upct(v, 1), color: "#FFB547" },
  { key: "breadth", label: "Breadth", sub: "watchlist EMA20 > EMA50", fmt: (v: number) => upct(v), color: "#3DD6FF" },
  { key: "volume", label: "Volume", sub: "vs 20d average", fmt: (v: number) => `${num(v, 2)}×`, color: "#9B7BFF" },
  { key: "momentum", label: "Momentum", sub: "avg 3-month return", fmt: (v: number) => pct(v, 1), color: "#3DFF8F" },
  { key: "dist_sma200", label: "Trend", sub: "SPY vs 200d MA", fmt: (v: number) => pct(v, 1), color: "#3DFF8F" },
];
export function Observable({ s, o }: { s: State; o: (typeof OBS)[number] }) {
  const x = s.observables?.[o.key];
  const v = x?.value as number | null | undefined;
  return (
    <div className="border border-edge bg-void/60 px-3 py-2" data-obs={o.key}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="label !text-ink">{o.label}</span>
        <span className="text-[14px] font-medium" style={{ color: o.color }}>{isNum(v) ? o.fmt(v) : "—"}</span>
      </div>
      <div className="label !text-[9px] !tracking-[0.1em]">{o.sub}</div>
      <Sparkline values={(x?.history ?? []) as (number | null)[]} color={o.color} />
    </div>
  );
}
