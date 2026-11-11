"use client";
// Connessione allo stato del bot: WebSocket (/ws) con ripiego sul polling di /api/state.
// Ogni numero mostrato viene da qui: se manca, i componenti mostrano "—".
import { useEffect, useRef, useState } from "react";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Num = number | null | undefined;
export type Verdict = {
  ts: string; symbol: string; action: string; intent: string; verdict: string; confidence: number; score: number;
  regime: string; strategy: string; reason: string; veto: string | null; price: number | null;
  stop: number | null; take_profit: number | null; components: Record<string, number>;
};
export type Point = { time: number; value: number };
export type LogLine = { ts: string; tag: string; text: string };
export type State = {
  empty: boolean; demo: boolean; mode?: string; updated?: string; halted: boolean; kill_requested?: boolean;
  session_paused?: boolean; paused_until?: string | null; cooldowns?: Record<string, string>;
  counters?: { trades_today: number; signals_today: number; blocked_today: number };
  account?: Record<string, any>; satellite_halted?: boolean; satellite_mode?: string; core_signal?: boolean | null;
  shadow_positions?: any[]; shadow_pnl?: number; shadow_trades?: number;
  equity?: Point[]; spy?: Point[]; drawdown?: Point[];
  positions?: any[]; verdicts?: Verdict[];
  observables?: Record<string, { value: any; history: any[]; reason?: string }>;
  life?: LogLine[];
  landing?: { symbol: string; bars: [string, number, number, number, number][]; entry: Num; stop: Num;
    take_profit: Num; side: string } | null;
  correlations?: { symbols: string[]; matrix: number[][] } | null;
  log?: LogLine[];
  strategies?: { stats: Record<string, any>; weights: Record<string, number>; weights_history: any[] };
  backtest?: any; ticker?: { symbol: string; price: Num; chg: Num }[]; market?: any; meetings?: any[];
  stats?: any; lessons?: string[]; limits?: Record<string, any>;
};

export function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API) return process.env.NEXT_PUBLIC_API;
  if (typeof window !== "undefined" && window.location.port === "3000") return "http://127.0.0.1:8000";
  return "";
}

export function useLive() {
  const [state, setState] = useState<State | null>(null);
  const [link, setLink] = useState<"ws" | "poll" | "down">("down");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    const base = apiBase();
    const poll = async () => {
      try {
        const r = await fetch(`${base}/api/state`, { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        setState(await r.json());
        setLink("poll");
      } catch {
        setLink("down");
      }
    };
    const startPolling = () => {
      if (timer.current) return;
      poll();
      timer.current = setInterval(poll, 5000);
    };
    try {
      const url = (base || window.location.origin).replace(/^http/, "ws") + "/ws";
      ws = new WebSocket(url);
      ws.onmessage = (e) => { setState(JSON.parse(e.data)); setLink("ws"); };
      ws.onerror = () => startPolling();
      ws.onclose = () => { if (!closed) startPolling(); };
    } catch {
      startPolling();
    }
    return () => {
      closed = true;
      ws?.close();
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  return { state, link };
}

export async function post(path: string, body?: unknown): Promise<boolean> {
  const r = await fetch(`${apiBase()}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  });
  return r.ok;
}
