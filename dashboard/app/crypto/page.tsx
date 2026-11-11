"use client";
// Dry-run crypto (PULSE-CT, criterio 7): stato giorno per giorno, avvisi, ordini simulati e costi misurati.
// Solo lettura di /api/crypto/dryrun. Mostra costi di esecuzione, mai rendimenti della strategia.
import { useEffect, useState } from "react";
import { apiBase, type Num } from "@/lib/live";
import { num, isNum } from "@/lib/fmt";
import { Panel } from "@/components/Panel";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Day = { day: string; status: "ok" | "missed" | "pending" | "unused"; issues: string[] };
type Order = {
  day: string; asset: string | null; side: string | null; status: string; mid: Num; fill: Num; coinbase_open: Num;
  delay_s: Num; exec_gap_bp: Num; venue_basis_bp: Num; spread_bp: Num; depth_bp: Record<string, Num> | null;
};
type DryRun = {
  planned: boolean; freqtrade_up: boolean; plan?: any; fingerprint_ok?: boolean; now?: string;
  next_decision?: string | null; valid_days?: number; missed_days?: number; needed?: number; max_missed?: number;
  state?: string; days?: Day[]; orders?: Order[]; report?: any; cost_cap_bp?: number; taker_bp?: number;
};

const DAY_COLOR: Record<Day["status"], string> = {
  ok: "#3DFF8F", missed: "#FF4D5E", pending: "#1c2430", unused: "#0f141c",
};
const STATE_COLOR: Record<string, string> = {
  "in attesa": "#6B7A90", "in corso": "#3DD6FF", completo: "#3DFF8F", fallito: "#FF4D5E",
};

function useDryRun() {
  const [d, setD] = useState<DryRun | null>(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${apiBase()}/api/crypto/dryrun`, { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        setD(await r.json());
        setDown(false);
      } catch {
        setDown(true);
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);
  return { d, down };
}

function Countdown({ to }: { to?: string | null }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!to || now === null) return <span className="text-mute">—</span>;
  let s = Math.max(0, Math.floor((new Date(to).getTime() - now) / 1000));
  const dd = Math.floor(s / 86400); s -= dd * 86400;
  const hh = Math.floor(s / 3600); s -= hh * 3600;
  const mm = Math.floor(s / 60); s -= mm * 60;
  const p = (x: number) => String(x).padStart(2, "0");
  return <span suppressHydrationWarning>{dd > 0 ? `${dd}g ` : ""}{p(hh)}:{p(mm)}:{p(s)}</span>;
}

function Stat({ label, children, color }: { label: string; children: React.ReactNode; color?: string }) {
  return (
    <div className="min-w-0">
      <div className="label">{label}</div>
      <div className="mt-1 text-[20px] font-medium leading-tight" style={{ color }}>{children}</div>
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = {
  ok: "eseguito", late: "in ritardo", okx_price_missing: "prezzo OKX mancante", order_failed: "ordine fallito",
  not_filled: "non eseguito",
};

const bp = (v: Num, d = 2) => (isNum(v) ? `${num(v, d)} bp` : "—");

export default function CryptoPage() {
  const { d, down } = useDryRun();
  const rep = d?.report;
  const state = d?.state ?? "—";

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-edge bg-void/90 backdrop-blur">
        <div className="flex flex-wrap items-center gap-4 px-4 py-2.5">
          <a href="/" className="text-[15px] font-medium tracking-[0.2em] text-ink hover:text-cyan">PULSE</a>
          <span className="label">// crypto trend · dry-run di riconciliazione</span>
          <span className="tag ml-auto" style={{ color: "#FFB547", borderColor: "#FFB547" }}>simulato · senza chiavi</span>
          <a href="/" className="label hover:text-cyan">command center</a>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-[1400px] flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-12">
        {down && !d && (
          <div className="col-span-full panel p-4 text-loss">API non raggiungibile: avvia python main.py app.</div>
        )}
        {!d && !down && (
          <div className="col-span-full grid min-h-[50vh] place-items-center text-mute">
            <span className="cursor">CONNECTING TO PULSE</span>
          </div>
        )}
        {d && !d.planned && (
          <div className="col-span-full">
            <Panel title="Dry-run" parts={["non pianificato"]} tag="IDLE" tagColor="#6B7A90">
              <p>Il piano non è ancora scritto. Si crea con:</p>
              <pre className="mt-2 text-cyan">python -m pulse_mm.research.crypto_trend dryrun start AAAA-MM-GG</pre>
            </Panel>
          </div>
        )}
        {d?.planned && (
          <>
            <div className="lg:col-span-12">
              <Panel title="Stato" parts={[`dal ${d.plan.start}`, `al massimo fino al ${d.plan.last_day_max}`]}
                     tag={state} tagColor={STATE_COLOR[state] ?? "#6B7A90"}>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                  <Stat label="Giorni validi" color="#3DFF8F">{d.valid_days} <span className="text-[12px] text-mute">/ {d.needed}</span></Stat>
                  <Stat label="Giorni saltati" color={(d.missed_days ?? 0) > 0 ? "#FFB547" : undefined}>
                    {d.missed_days} <span className="text-[12px] text-mute">/ {d.max_missed} recuperabili</span>
                  </Stat>
                  <Stat label="Prossimo ordine" color="#3DD6FF"><Countdown to={d.next_decision} /></Stat>
                  <Stat label="freqtrade" color={d.freqtrade_up ? "#3DFF8F" : "#FF4D5E"}>{d.freqtrade_up ? "acceso" : "spento"}</Stat>
                  <Stat label="Impronta del piano" color={d.fingerprint_ok ? "#3DFF8F" : "#FF4D5E"}>
                    <span className="text-[14px]">{d.plan.fingerprint}</span>
                    <div className="text-[11px] text-mute">{d.fingerprint_ok ? "codice invariato" : "codice cambiato: dry-run non valido"}</div>
                  </Stat>
                  <Stat label="Ordine di prova">
                    <span className="text-[14px]">{num(d.plan.stake_usdc, 0)} USDC</span>
                    <div className="text-[11px] text-mute">BTC e ETH alle 00:05 UTC</div>
                  </Stat>
                </div>
              </Panel>
            </div>

            <div className="lg:col-span-7">
              <Panel title="Calendario" parts={["un quadrato per giorno", "verde valido · rosso saltato"]}>
                <div className="grid grid-cols-7 gap-1.5 sm:grid-cols-11">
                  {d.days?.map((x) => (
                    <div key={x.day} title={`${x.day}${x.issues.length ? ": " + x.issues.join("; ") : ""}`}
                         className="aspect-square border border-edge p-1 text-[9px] leading-none"
                         style={{ background: DAY_COLOR[x.status] + (x.status === "ok" || x.status === "missed" ? "33" : ""),
                                  borderColor: x.status === "ok" || x.status === "missed" ? DAY_COLOR[x.status] : undefined }}>
                      <span className={x.status === "unused" ? "text-edge" : "text-mute"}>{x.day.slice(8)}/{x.day.slice(5, 7)}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-mute">
                  Un giorno saltato si recupera in coda. Al {(d.max_missed ?? 3) + 1}° giorno saltato il dry-run fallisce e riparte da zero.
                </p>
              </Panel>
            </div>

            <div className="lg:col-span-5">
              <Panel title="Avvisi" parts={["controllo giornaliero"]}
                     tag={d.days?.some((x) => x.status === "missed") ? "da guardare" : "nessuno"}
                     tagColor={d.days?.some((x) => x.status === "missed") ? "#FFB547" : "#3DFF8F"}>
                {d.days?.filter((x) => x.status === "missed").length ? (
                  <ul className="space-y-2">
                    {d.days.filter((x) => x.status === "missed").map((x) => (
                      <li key={x.day}>
                        <span className="text-amber">{x.day}</span>
                        <ul className="ml-3 text-mute">{x.issues.map((i) => <li key={i}>{i}</li>)}</ul>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-mute">Nessun giorno saltato. Qui compaiono ordini non partiti, prezzi OKX mancanti, ritardi e aperture Coinbase mancanti.</p>
                )}
              </Panel>
            </div>

            <div className="lg:col-span-5">
              <Panel title="Costi misurati" parts={[`${rep?.orders ?? 0} ordini`, "limite basso"]}>
                <table className="w-full">
                  <tbody className="[&_td]:py-1 [&_td:last-child]:text-right">
                    <tr><td className="text-mute">Scarto di esecuzione medio</td>
                      <td className={isNum(rep?.exec_gap_bp_mean) && rep.exec_gap_bp_mean > (d.cost_cap_bp ?? 10) ? "text-loss" : "text-ink"}>
                        {bp(rep?.exec_gap_bp_mean)} <span className="text-mute">/ tetto {bp(d.cost_cap_bp, 0)}</span></td></tr>
                    <tr><td className="text-mute">Scarto di esecuzione massimo</td><td>{bp(rep?.exec_gap_bp_max)}</td></tr>
                    <tr><td className="text-mute">Differenza OKX − Coinbase</td><td>{bp(rep?.venue_basis_bp_mean)}</td></tr>
                    <tr><td className="text-mute">Spread OKX medio · massimo</td><td>{bp(rep?.spread_bp_mean)} · {bp(rep?.spread_bp_max)}</td></tr>
                    {["x1", "x5", "x10"].map((k) => (
                      <tr key={k}><td className="text-mute">Costo sul book, taglia ×{k.slice(1)}</td>
                        <td>{bp(rep?.depth_cost_by_size?.[k]?.mean_bp)}</td></tr>
                    ))}
                    <tr><td className="text-mute">Commissione taker OKX (a parte)</td><td>{bp(d.taker_bp, 0)}</td></tr>
                  </tbody>
                </table>
                <p className="mt-3 text-mute">
                  Ordini simulati sul book: verificano la catena e la differenza fra sedi, non lo slippage vero.
                  L&apos;esito del criterio si legge solo a dry-run completo.
                </p>
              </Panel>
            </div>

            <div className="lg:col-span-7">
              <Panel title="Ordini" parts={["più recenti in alto"]} bodyClass="p-0 overflow-x-auto">
                {d.orders?.length ? (
                  <table className="w-full min-w-[640px]">
                    <thead><tr className="label [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-normal">
                      <th>Giorno</th><th>Asset</th><th>Lato</th><th>Esito</th><th>Medio OKX</th><th>Eseguito</th><th>Scarto</th><th>Spread</th>
                    </tr></thead>
                    <tbody className="[&_td]:border-t [&_td]:border-edge [&_td]:px-3 [&_td]:py-1.5">
                      {d.orders.map((o, i) => (
                        <tr key={i}>
                          <td>{o.day}</td><td>{o.asset ?? "—"}</td>
                          <td className={o.side === "buy" ? "text-gain" : o.side === "sell" ? "text-loss" : "text-mute"}>
                            {o.side === "buy" ? "acquisto" : o.side === "sell" ? "vendita" : "—"}</td>
                          <td className={o.status === "ok" ? "text-ink" : "text-amber"}>{STATUS_LABEL[o.status] ?? o.status}</td>
                          <td>{num(o.mid, 2)}</td><td>{num(o.fill, 2)}</td>
                          <td>{bp(o.exec_gap_bp)}</td><td>{bp(o.spread_bp, 3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="p-3 text-mute">Nessun ordine ancora. Il primo parte alle 00:05 UTC del {d.plan.start}.</p>
                )}
              </Panel>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
