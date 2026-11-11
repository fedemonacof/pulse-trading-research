"use client";
import { useEffect, useRef, useState } from "react";
import { post, type State } from "@/lib/live";
import { pct, upct, REGIME_LABEL, REGIME_COLOR } from "@/lib/fmt";

function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="text-right leading-none">
      <div className="text-[18px] sm:text-[26px] font-light tracking-tight text-ink glow-cyan" suppressHydrationWarning>
        {now ? now.toISOString().slice(11, 19) : "--:--:--"} <span className="text-[11px] text-mute">UTC</span>
      </div>
      <div className="label mt-1" suppressHydrationWarning>{now ? now.toISOString().slice(0, 10) : ""}</div>
    </div>
  );
}

function Counter({ label, value, color }: { label: string; value: number | undefined; color: string }) {
  return (
    <div className="px-2 sm:px-4 border-l border-edge first:border-l-0 sm:first:border-l">
      <div className="label">{label}</div>
      <div className="text-[20px] font-medium leading-tight" style={{ color }}>{value ?? "—"}</div>
    </div>
  );
}

export function TopBar({ s, link }: { s: State | null; link: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [msg, setMsg] = useState("");
  const regime = s?.observables?.regime?.value as string | undefined;
  const say = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 3500); };

  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-void/90 backdrop-blur">
      <div className="flex flex-wrap items-center gap-4 px-4 py-2.5">
        <div className="grid h-10 w-10 place-items-center border border-cyan bg-cyan/10 text-[15px] font-bold text-cyan glow-cyan">PS</div>
        <div className="min-w-0">
          <div className="flex items-baseline gap-2 text-[15px] font-bold tracking-[0.18em]">
            <span className="text-cyan glow-cyan">PULSE</span><span className="text-mute">//</span>
            <span className="text-ink">AUTONOMOUS EQUITY AGENT</span>
          </div>
          <div className="label mt-0.5 flex flex-wrap gap-x-2">
            <span>US EQUITIES · ETF</span><span>·</span>
            <span>REGIME <b style={{ color: REGIME_COLOR[regime ?? ""] ?? "#6B7A90" }}>{REGIME_LABEL[regime ?? ""] ?? "—"}</b></span>
            <span>·</span><span>FEED {link === "ws" ? "WEBSOCKET" : link === "poll" ? "POLLING" : "OFFLINE"}</span>
            {s?.demo && <><span>·</span><span className="text-amber">DATI DEMO</span></>}
          </div>
        </div>
        <div className="flex w-full min-w-0 flex-wrap items-center gap-y-2 sm:ml-auto sm:w-auto">
          <Counter label="Trades today" value={s?.counters?.trades_today} color="#D7E0EA" />
          <Counter label="Signals" value={s?.counters?.signals_today} color="#3DD6FF" />
          <Counter label="Blocked by risk" value={s?.counters?.blocked_today} color="#FF4D5E" />
          <div className="ml-auto px-2 sm:px-4 sm:border-l border-edge"><Clock /></div>
        </div>
        <div className="flex items-center gap-2">
          <span className="tag !text-[10px] !py-1" style={{
            color: s?.mode === "LIVE" ? "#FF4D5E" : "#3DFF8F", borderColor: s?.mode === "LIVE" ? "#FF4D5E" : "#3DFF8F",
          }}>{s?.mode ?? "—"}</span>
          {s?.kill_requested ? (
            <button className="tag !text-[11px] !py-1.5 !px-3 text-amber border-amber" onClick={async () => {
              say((await post("/api/kill/cancel")) ? "Kill switch annullato" : "Operazione non riuscita");
            }}>ANNULLA KILL</button>
          ) : s?.halted ? (
            <button className="tag !text-[11px] !py-1.5 !px-3 text-gain border-gain" onClick={async () => {
              say((await post("/api/resume")) ? "Bot riattivato" : "Operazione non riuscita");
            }}>RIATTIVA</button>
          ) : (
            <button
              className="border border-loss bg-loss/15 px-3 py-1.5 text-[11px] font-bold tracking-[0.16em] text-loss hover:bg-loss/30"
              style={{ boxShadow: "0 0 16px rgba(255,77,94,.35)" }}
              onClick={() => dialog.current?.showModal()}
            >KILL SWITCH</button>
          )}
        </div>
      </div>
      {msg && <div role="status" className="absolute right-4 top-full mt-2 border border-edge bg-panel px-3 py-2">{msg}</div>}

      <dialog ref={dialog} className="panel m-auto max-w-md p-5 text-ink backdrop:bg-black/70"
        onClose={async () => {
          if (dialog.current?.returnValue === "confirm")
            say((await post("/api/kill", { confirm: true })) ? "Kill switch inviato: il bot cancella e chiude tutto entro un minuto" : "Operazione non riuscita");
        }}>
        <form method="dialog">
          <div className="label !text-loss">KILL SWITCH // CONFERMA</div>
          <p className="mt-3 text-[13px] leading-relaxed">
            Il bot cancella tutti gli ordini aperti, chiude tutte le posizioni a mercato al prossimo controllo
            (entro un minuto) e si ferma finché non lo riattivi.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button value="cancel" className="tag !text-[11px] !py-1.5 !px-3 text-mute border-edge">Annulla</button>
            <button value="confirm" className="border border-loss bg-loss/20 px-3 py-1.5 text-[11px] font-bold tracking-[0.14em] text-loss">
              Cancella e chiudi tutto
            </button>
          </div>
        </form>
      </dialog>
    </header>
  );
}

export function Tape({ s, bottom = false }: { s: State | null; bottom?: boolean }) {
  let items: { k: string; text: string; color: string }[] = [];
  if (!bottom) {
    items = (s?.ticker ?? []).map((t) => ({
      k: t.symbol, text: `${t.symbol} ${typeof t.price === "number" ? t.price.toFixed(2) : "—"} ${pct(t.chg)}`,
      color: (t.chg ?? 0) >= 0 ? "#3DFF8F" : "#FF4D5E",
    }));
    const vetoes = (s?.log ?? []).filter((l) => l.tag === "VETO").slice(0, 6);
    items = items.concat(vetoes.map((v, i) => ({ k: `v${i}`, text: `VETO ${v.text}`, color: "#FF4D5E" })));
  } else {
    const a = s?.account ?? {}, l = s?.limits ?? {};
    items = [
      { k: "exp", text: `EXPOSURE ${upct(a.gross)} / ${upct(l.max_gross_exposure_pct)}`, color: "#3DD6FF" },
      { k: "loss", text: `DAILY LOSS USED ${upct(a.loss_used)} OF ${upct(l.max_daily_loss_pct, 1)}`, color: (a.loss_used ?? 0) > 0.5 ? "#FF4D5E" : "#FFB547" },
      { k: "pos", text: `OPEN POSITIONS ${s?.positions?.length ?? "—"} / ${l.max_open_positions ?? "—"}`, color: "#D7E0EA" },
      { k: "size", text: `MAX SIZE ${upct(l.max_position_pct)} EQUITY`, color: "#9B7BFF" },
      { k: "dd", text: `DRAWDOWN ${pct(a.drawdown)} · MAX ${pct(a.max_drawdown)}`, color: "#FF4D5E" },
      { k: "br", text: `BRACKET ${l.stop_loss_atr_mult ?? "—"}×ATR STOP / ${l.take_profit_atr_mult ?? "—"}×ATR TARGET`, color: "#FFB547" },
      { k: "w", text: `WEIGHTS ${Object.entries(s?.strategies?.weights ?? {}).map(([k, v]) => `${k.toUpperCase()} ${v.toFixed(2)}`).join(" · ") || "—"}`, color: "#3DD6FF" },
      { k: "st", text: s?.halted ? "KILL SWITCH ACTIVE" : s?.session_paused ? "SESSION PAUSED: DAILY LOSS LIMIT" : "RISK LAYER ARMED", color: s?.halted || s?.session_paused ? "#FF4D5E" : "#3DFF8F" },
    ];
  }
  const row = items.length ? items : [{ k: "none", text: "NESSUN DATO", color: "#6B7A90" }];
  return (
    <div className={`flex items-center overflow-hidden border-edge bg-panel ${bottom ? "border-t" : "border-b"}`}>
      <div className={`z-10 flex shrink-0 items-center gap-2 px-3 py-1.5 font-bold tracking-[0.16em] ${bottom ? "bg-violet/15 text-violet" : "bg-loss/15 text-loss"}`}>
        {!bottom && <span className="live-dot" />}{bottom ? "RISK" : "LIVE FEED"}
      </div>
      <div className="min-w-0 flex-1 overflow-hidden">
        <div className="tape">
          {[0, 1].map((dup) => (
            <div key={dup} className="flex shrink-0" aria-hidden={dup === 1}>
              {row.map((it) => (
                <span key={it.k + dup} className="whitespace-nowrap px-4 py-1.5" style={{ color: it.color }}>
                  {it.text}<span className="ml-4 text-edge">|</span>
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
