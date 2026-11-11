"use client";
import { useEffect, useRef, useState } from "react";

const still = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Il numero "scorre" fino al nuovo valore (tick-up). Con movimento ridotto salta direttamente. */
export function useTween(target: number | null | undefined, ms = 900): number | null {
  const [v, setV] = useState<number | null>(typeof target === "number" ? target : null);
  const from = useRef<number | null>(v);
  useEffect(() => {
    if (typeof target !== "number" || !Number.isFinite(target)) { setV(null); return; }
    const start = from.current ?? target;
    if (still() || start === target) { from.current = target; setV(target); return; }
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      const x = start + (target - start) * e;
      setV(x);
      from.current = x;
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

/** Restituisce true per un attimo ogni volta che il valore cresce (es. un ordine eseguito). */
export function usePulse(value: number | undefined): boolean {
  const [on, setOn] = useState(false);
  const prev = useRef(value);
  useEffect(() => {
    if (value !== undefined && prev.current !== undefined && value > prev.current) {
      setOn(true);
      const t = setTimeout(() => setOn(false), 1200);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  return on;
}
