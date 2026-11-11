"use client";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Panel } from "./Panel";
import type { State } from "@/lib/live";
import { hhmm, num, pct, sUsd, upct, tone, VERDICT_COLOR, isNum } from "@/lib/fmt";

// ------------------------------------------------------------ CORRELATION MAP
export function CorrelationMap({ s }: { s: State }) {
  const c = s.correlations;
  const held = new Set((s.positions ?? []).map((p) => p.symbol));
  const W = 300, R = 115, cx = W / 2, cy = W / 2;
  const syms = c?.symbols ?? [];
  const pos = syms.map((_, i) => {
    const a = (i / Math.max(syms.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return [cx + Math.cos(a) * R, cy + Math.sin(a) * R];
  });
  const lines: { x1: number; y1: number; x2: number; y2: number; r: number; hot: boolean }[] = [];
  syms.forEach((a, i) => syms.forEach((b, j) => {
    if (j <= i) return;
    const r = c!.matrix[i][j];
    const hot = held.has(a) && held.has(b);
    if (Math.abs(r) >= 0.5 || (hot && Math.abs(r) >= 0.2))
      lines.push({ x1: pos[i][0], y1: pos[i][1], x2: pos[j][0], y2: pos[j][1], r, hot });
  }));
  const heldPairs = lines.filter((l) => l.hot);
  const avg = heldPairs.length ? heldPairs.reduce((t, l) => t + l.r, 0) / heldPairs.length : null;
  return (
    <Panel title="Correlation map" parts={["60d returns", "|ρ| ≥ 0.5"]} tag={held.size ? `${held.size} HOLDINGS` : "FLAT"} tagColor="#9B7BFF">
      {syms.length ? (
        <>
          <svg viewBox={`0 0 ${W} ${W}`} className="mx-auto block w-full max-w-[300px]" role="img"
            aria-label="Rete circolare delle correlazioni tra i titoli">
            <circle cx={cx} cy={cy} r={R} fill="none" stroke="#1C2430" />
            <circle cx={cx} cy={cy} r={R * 0.55} fill="none" stroke="#1C2430" strokeDasharray="2 4" />
            {lines.map((l, i) => (
              <line key={i} {...l} stroke={l.r >= 0 ? (l.hot ? "#FF4D5E" : "#3DD6FF") : "#3DFF8F"}
                strokeWidth={l.hot ? 1.8 : 0.8} opacity={l.hot ? 0.9 : 0.25 + Math.abs(l.r) * 0.3}
                style={l.hot ? { filter: "drop-shadow(0 0 3px #FF4D5E)" } : undefined} />
            ))}
            {syms.map((sym, i) => (
              <g key={sym}>
                <circle cx={pos[i][0]} cy={pos[i][1]} r={held.has(sym) ? 5 : 3} fill={held.has(sym) ? "#FFB547" : "#6B7A90"}
                  style={held.has(sym) ? { filter: "drop-shadow(0 0 5px #FFB547)" } : undefined} />
                <text x={pos[i][0] + (pos[i][0] >= cx ? 8 : -8)} y={pos[i][1] + 3} fontSize="9"
                  textAnchor={pos[i][0] >= cx ? "start" : "end"} fill={held.has(sym) ? "#FFB547" : "#6B7A90"}>{sym}</text>
              </g>
            ))}
          </svg>
          <p className="mt-1 text-[10.5px] text-mute">
            Correlazione media tra le posizioni aperte: <b className={avg !== null && avg > 0.6 ? "text-loss" : "text-ink"}>{num(avg)}</b>
            {avg !== null && avg > 0.6 ? " · rischio concentrato" : ""}
          </p>
        </>
      ) : <p className="text-mute">—</p>}
    </Panel>
  );
}

// ------------------------------------------------------------ AGENT LOG
const LOG_COLOR: Record<string, string> = { ...VERDICT_COLOR, COMMITTEE: "#9B7BFF", FILL: "#3DFF8F", HALT: "#FF4D5E",
  SESSION_PA: "#FF4D5E", STOPLOSS_G: "#FFB547", NIGHTLY_RE: "#3DD6FF", REFLECTION: "#9B7BFF" };
export function AgentLog({ s }: { s: State }) {
  const log = s.log ?? [];
  return (
    <Panel title="Agent log" parts={["tail -f agent.log"]} tag="LIVE" tagColor="#3DFF8F" bodyClass="p-0">
      <div className="h-[340px] overflow-y-auto px-3 py-2 text-[10.5px] leading-[1.55]" role="log" aria-live="polite">
        <div className="text-mute">pulse@desk:~$ tail -f agent.log</div>
        {[...log].reverse().map((l, i) => (
          <div key={i} className="grid grid-cols-[58px_74px_1fr] gap-2">
            <span className="text-mute">{hhmm(l.ts)}</span>
            <span style={{ color: LOG_COLOR[l.tag] ?? "#D7E0EA" }}>{l.tag}</span>
            <span className="truncate text-ink/85" title={l.text}>{l.text}</span>
          </div>
        ))}
        <div className="cursor text-mute">pulse@desk:~$</div>
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------ STRATEGY ENGINE
export function StrategyEngine({ s }: { s: State }) {
  const st = s.strategies?.stats ?? {};
  const w = s.strategies?.weights ?? {};
  const names = Object.keys(st);
  const total = s.stats ?? {};
  return (
    <Panel title="Strategy engine" parts={["Live trades", "Weights"]} tag={`${total.count ?? 0} CLOSED`} tagColor="#FFB547">
      <div className="grid grid-cols-3 gap-2 border-b border-edge pb-3">
        <div><div className="label">Win rate</div><div className="text-[26px] font-light text-ink">{upct(total.win_rate)}</div></div>
        <div><div className="label">Profit factor</div>
          <div className={`text-[26px] font-light ${(total.profit_factor ?? 0) >= 1 ? "text-gain" : "text-loss"}`}>{num(total.profit_factor)}</div></div>
        <div><div className="label">Avg win / loss</div>
          <div className="mt-1 text-[12px]"><span className="text-gain">{sUsd(total.avg_win)}</span> / <span className="text-loss">{sUsd(total.avg_loss)}</span></div></div>
      </div>
      <div className="mt-2 space-y-3">
        {names.length ? names.map((n) => {
          const x = st[n];
          return (
            <div key={n}>
              <div className="flex items-baseline gap-3 text-[11px]">
                <b className="w-16 uppercase tracking-[0.12em] text-cyan">{n}</b>
                <span className="text-mute">{x.trades} trades</span>
                <span>WR <b className="text-ink">{upct(x.win_rate)}</b></span>
                <span>PF <b className={(x.profit_factor ?? 0) >= 1 ? "text-gain" : "text-loss"}>{num(x.profit_factor)}</b></span>
                <span className={`ml-auto ${tone(x.pnl)}`}>{sUsd(x.pnl)}</span>
                <span className="text-violet">w {isNum(w[n]) ? w[n].toFixed(2) : "—"}</span>
              </div>
              <div className="h-[38px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={x.pnls.map((p: number, i: number) => ({ i, p }))} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
                    <XAxis dataKey="i" hide /><YAxis hide />
                    <Tooltip cursor={false} contentStyle={{ background: "#0A0E14", border: "1px solid #1C2430", fontSize: 10 }}
                      formatter={(v) => [sUsd(Number(v), 2), "P&L"]} labelFormatter={() => ""} />
                    <Bar dataKey="p" isAnimationActive={false}>
                      {x.pnls.map((p: number, i: number) => <Cell key={i} fill={p >= 0 ? "#3DFF8F" : "#FF4D5E"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        }) : <p className="text-mute">Nessun trade chiuso ancora.</p>}
        <p className="text-[10px] text-mute">
          Committee weight <b className="text-violet">{isNum(w.committee) ? w.committee.toFixed(2) : "—"}</b> (max 0.50) ·
          i pesi cambiano solo nella revisione notturna, entro limiti fissi.
        </p>
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------ COUNCIL (il comitato AI che vota)
export function Council({ s }: { s: State }) {
  const m = s.meetings?.[0];
  const stances = Object.entries(m?.stances ?? {}) as [string, { score: number; reason: string }][];
  return (
    <Panel title="AI council" parts={["8 agents", "Votes into the reflex"]} tag={m ? hhmm(m.ts) : "NO MEETING"} tagColor="#9B7BFF">
      {m ? (
        <>
          <p className="text-[12.5px] leading-snug text-ink">{m.market_view ?? "—"}</p>
          <div className="mt-3 space-y-1">
            {stances.length ? stances.sort((a, b) => Math.abs(b[1].score) - Math.abs(a[1].score)).map(([sym, x]) => (
              <div key={sym} className="grid grid-cols-[48px_1fr_44px] items-center gap-2 text-[11px]">
                <b>{sym}</b>
                <span className="relative h-1.5 bg-edge/60">
                  <span className="absolute inset-y-0 left-1/2 w-px bg-mute" />
                  <span className="absolute inset-y-0" style={{
                    left: x.score >= 0 ? "50%" : `${50 + x.score / 2}%`, width: `${Math.abs(x.score) / 2}%`,
                    background: x.score >= 0 ? "#3DFF8F" : "#FF4D5E", boxShadow: `0 0 6px ${x.score >= 0 ? "#3DFF8F" : "#FF4D5E"}`,
                  }} />
                </span>
                <span className={`text-right ${tone(x.score)}`}>{x.score > 0 ? "+" : ""}{Math.round(x.score)}</span>
              </div>
            )) : <p className="text-mute">Nessun voto sopra la confidenza minima.</p>}
          </div>
          <p className="mt-3 text-[10px] text-mute">Il voto pesa al massimo il 50% e non apre posizioni da solo: decide il riflesso, poi il risk layer.</p>
        </>
      ) : <p className="text-mute">Il comitato non si è ancora riunito (serve la chiave Anthropic).</p>}
    </Panel>
  );
}

// ------------------------------------------------------------ BACKTEST
export function BacktestPanel({ s }: { s: State }) {
  const b = s.backtest;
  if (!b) return (
    <Panel title="Backtest" parts={["Walk-forward", "vs SPY"]} tag="NOT RUN" tagColor="#6B7A90">
      <p className="text-mute">Esegui <code className="text-ink">python main.py backtest</code> per vedere qui i risultati.</p>
    </Panel>
  );
  const row = (k: string, x: { total_return: number; sharpe: number; max_drawdown: number }) => (
    <tr key={k} className="border-t border-edge/70">
      <td className="py-1 pr-2">{k}</td>
      <td className={`text-right ${tone(x.total_return)}`}>{pct(x.total_return, 1)}</td>
      <td className="text-right">{num(x.sharpe)}</td>
      <td className="text-right text-loss">{pct(x.max_drawdown, 1)}</td>
    </tr>
  );
  return (
    <Panel title="Backtest" parts={[b.source ?? "—", `${b.period?.from} → ${b.period?.to}`]} tag={b.beats_spy ? "BEATS SPY" : "DOES NOT BEAT SPY"}
      tagColor={b.beats_spy ? "#3DFF8F" : "#FF4D5E"}>
      <table className="w-full text-[11px]">
        <thead><tr className="label"><th className="text-left font-normal">Out of sample</th><th className="text-right font-normal">Total</th>
          <th className="text-right font-normal">Sharpe</th><th className="text-right font-normal">Max DD</th></tr></thead>
        <tbody>
          {row(b.core?.enabled ? "PULSE core + satellite" : "PULSE (reflex only)", b.strategy)}
          {row("SPY buy & hold", b.spy)}
          {row(`SPY @ ${upct(b.strategy?.exposure)} exposure`, b.spy_same_exposure)}
        </tbody>
      </table>
      <p className="mt-2 text-[10.5px] text-mute">
        {b.active ? <>active vs SPY <b className={tone(b.active.return)}>{pct(b.active.return, 1)}</b> · IR {num(b.active.information_ratio)} · </> : null}
        {b.trades?.count ?? 0} trade · win {upct(b.trades?.win_rate)} · PF {num(b.trades?.profit_factor)} ·
        costi {b.costs?.commission_bps}+{b.costs?.slippage_bps} bps · comitato AI escluso dal backtest
      </p>
      <p className={`mt-1 text-[11px] ${b.beats_spy ? "text-gain" : "text-loss"}`}>{b.verdict}</p>
    </Panel>
  );
}
