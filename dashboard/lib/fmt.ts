import type { Num } from "./live";

const nf = (d: number) => new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const ok = (v: Num): v is number => typeof v === "number" && Number.isFinite(v);

export const num = (v: Num, d = 2) => (ok(v) ? nf(d).format(v) : "—");
export const usd = (v: Num, d = 0) => (ok(v) ? `$${nf(d).format(v)}` : "—");
export const sUsd = (v: Num, d = 0) => (ok(v) ? `${v > 0 ? "+" : v < 0 ? "−" : ""}$${nf(d).format(Math.abs(v))}` : "—");
export const pct = (v: Num, d = 2) => (ok(v) ? `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(d).format(Math.abs(v * 100))}%` : "—");
export const upct = (v: Num, d = 0) => (ok(v) ? `${nf(d).format(v * 100)}%` : "—");
export const tone = (v: Num) => (ok(v) ? (v > 0 ? "text-gain" : v < 0 ? "text-loss" : "text-ink") : "text-mute");
export const hhmm = (iso?: string) => (iso ? iso.slice(11, 19) : "--:--:--");
export const isNum = ok;

export const VERDICT_COLOR: Record<string, string> = {
  BUY: "#3DFF8F", SELL: "#FF4D5E", EXIT: "#3DD6FF", VETO: "#FF4D5E", HOLD: "#9B7BFF", SKIP: "#6B7A90",
};
export const REGIME_COLOR: Record<string, string> = {
  trending: "#3DFF8F", mean_reverting: "#3DD6FF", high_vol: "#FFB547", crisis: "#FF4D5E", warming_up: "#6B7A90",
};
export const REGIME_LABEL: Record<string, string> = {
  trending: "TRENDING", mean_reverting: "MEAN REVERTING", high_vol: "HIGH VOL", crisis: "CRISIS", warming_up: "WARMING UP",
};
