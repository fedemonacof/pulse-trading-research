"""Server del command center PULSE: API JSON + WebSocket sul diario del bot, più la dashboard Next.js
esportata (dashboard/out). Ascolta solo su 127.0.0.1.

    python main.py app                 # http://127.0.0.1:8000, diario journal.db
    DB_PATH=demo.db python main.py app # diario demo

Non invia mai ordini: il kill switch scrive una richiesta nel diario, che il bot esegue al tick
successivo (cancella tutti gli ordini e chiude tutte le posizioni).
Ogni numero viene dal diario o dall'ultimo backtest: se un dato manca, vale None (la dashboard mostra "—").
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import RiskLimits, load_settings
from .journal import Journal
from .reflex import clamp_weights

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT / "dashboard" / "out"
EXIT_KINDS = re.compile(r"^(stop loss|trailing stop|take profit|chiusura|ribilanciamento|halt|chiudo)")


def _ts(s: str) -> int:
    return int(datetime.fromisoformat(s).timestamp())


def _num(x):
    return None if x is None else float(x)


def _series(rows, key, n=60):
    return [r.get(key) for r in rows[-n:]]


def build_state(j: Journal, limits: RiskLimits) -> dict:
    now = datetime.now(timezone.utc)
    eq = j.rows("SELECT ts, mode, equity, cash, spy FROM equity WHERE mode != 'SHADOW' ORDER BY ts")
    if not eq:
        return {"empty": True, "demo": bool(j.get("demo")), "halted": bool(j.get("halted")),
                "backtest": j.get("last_backtest")}

    last, first = eq[-1], eq[0]
    peak, max_dd, series, spy_series, dd_series = 0.0, 0.0, {}, {}, {}
    spy0 = next((r["spy"] for r in eq if r["spy"]), None)
    for r in eq:
        peak = max(peak, r["equity"])
        max_dd = min(max_dd, r["equity"] / peak - 1)
        t = _ts(r["ts"])                                # un punto per secondo: tempi strettamente crescenti
        series[t] = {"time": t, "value": round(r["equity"], 2)}
        dd_series[t] = {"time": t, "value": round(r["equity"] / peak - 1, 5)}
        if spy0 and r["spy"]:
            spy_series[t] = {"time": t, "value": round(first["equity"] * r["spy"] / spy0, 2)}
    day = last["ts"][:10]
    day_start = next((r["equity"] for r in eq if r["ts"][:10] == day), last["equity"])
    day_ret = last["equity"] / day_start - 1

    entries = j.get("entries", {})
    peaks = j.get("peaks", {})
    positions = []
    for p in j.get("positions", []):
        d = 1 if p["qty"] > 0 else -1
        meta = entries.get(p["symbol"], {})
        positions.append({
            "symbol": p["symbol"], "side": "long" if d > 0 else "short", "qty": p["qty"],
            "avg": p["avg_price"], "price": p["market_price"], "peak": peaks.get(p["symbol"]),
            "weight": p["qty"] * p["market_price"] / last["equity"],
            "pnl": (p["market_price"] - p["avg_price"]) * p["qty"],
            "pnl_pct": (p["market_price"] / p["avg_price"] - 1) * d,
            "stop": meta.get("stop"), "take_profit": meta.get("take_profit"),
            "regime": meta.get("regime"), "strategy": meta.get("strategy"), "confidence": meta.get("confidence"),
            "reason": meta.get("reason", ""), "opened": meta.get("ts"),
        })
    gross = sum(abs(p["weight"]) for p in positions)

    # --- Pila dei verdetti: l'ultima decisione del riflesso per ogni titolo ---
    verdicts = j.rows("""SELECT d.* FROM decisions d JOIN (SELECT symbol, MAX(ts) m FROM decisions GROUP BY symbol) x
                         ON d.symbol = x.symbol AND d.ts = x.m ORDER BY d.confidence DESC""")
    seen, stack = set(), []
    for v in verdicts:
        if v["symbol"] in seen:
            continue
        seen.add(v["symbol"])
        v["components"] = json.loads(v["components"] or "{}")
        stack.append(v)

    # --- Osservabili con storico per gli sparkline ---
    obs_rows = [json.loads(r["payload"]) | {"ts": r["ts"]}
                for r in j.rows("SELECT ts, payload FROM observables ORDER BY ts DESC LIMIT 80")][::-1]
    latest_obs = obs_rows[-1] if obs_rows else {}
    observables = {k: {"value": latest_obs.get(k), "history": _series(obs_rows, k)}
                   for k in ("volatility", "breadth", "volume", "momentum", "atr_pct", "dist_sma200")}
    observables["regime"] = {"value": latest_obs.get("regime"), "reason": latest_obs.get("regime_reason"),
                             "history": _series(obs_rows, "regime")}

    # --- Comitato e mercato ---
    meetings, market, snaps = [], {}, {}
    for m in j.rows("SELECT ts, payload FROM events WHERE kind='committee' ORDER BY ts DESC LIMIT 12"):
        p = json.loads(m["payload"])
        d = p.get("decision") or {}
        meetings.append({"ts": m["ts"], "market_view": d.get("market_view"), "targets": d.get("targets", []),
                         "reports": p.get("reports", {}), "stances": p.get("stances", {})})
        if not market:
            snaps = p.get("snapshots", {})
            ctx = p.get("context") or {}
            market = {"macro": ctx.get("macro") or {}, "calendar": ctx.get("calendario") or [],
                      "fundamentals": ctx.get("fondamentali") or {}, "headlines": p.get("headlines") or [],
                      "missing": ctx.get("fonti_non_disponibili") or []}
    live = {p["symbol"]: p["price"] for p in positions}
    last_px = {v["symbol"]: v["price"] for v in stack}
    ticker = [{"symbol": s, "price": live.get(s, last_px.get(s, v.get("price"))), "chg": v.get("chg_1d")}
              for s, v in snaps.items()]

    # --- Trade, strategie, contatori ---
    trades = j.rows("SELECT ts, symbol, direction, qty, entry, exit, pnl, pnl_pct, reason, thesis, regime, strategy,"
                    " confidence, entry_ts, holding_minutes FROM closed_trades ORDER BY ts DESC")
    by_strategy = {}
    for t in trades:
        s = by_strategy.setdefault(t["strategy"] or "altro", {"trades": 0, "wins": 0, "gross_win": 0.0,
                                                              "gross_loss": 0.0, "pnl": 0.0, "pnls": []})
        s["trades"] += 1
        s["wins"] += t["pnl"] > 0
        s["pnl"] += t["pnl"]
        s["gross_win" if t["pnl"] > 0 else "gross_loss"] += abs(t["pnl"])
        s["pnls"].append(round(t["pnl"], 2))
    for s in by_strategy.values():
        s["win_rate"] = s["wins"] / s["trades"]
        s["profit_factor"] = s["gross_win"] / s["gross_loss"] if s["gross_loss"] else None
        s["pnls"] = s["pnls"][:30][::-1]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] < 0]
    by_exit = {}
    for t in trades:
        m = EXIT_KINDS.match(t["reason"] or "")
        k = m.group(1) if m else "altro"
        by_exit[k] = by_exit.get(k, 0) + t["pnl"]

    today = (j.rows("SELECT ts FROM equity WHERE mode != 'SHADOW' ORDER BY ts DESC LIMIT 1")[0]["ts"])[:10]
    counters = {
        "trades_today": j.db_query("SELECT COUNT(*) FROM orders WHERE ts >= ? AND status IN ('submitted','filled')",
                                   (today,))[0][0],
        "signals_today": j.db_query("SELECT COUNT(*) FROM decisions WHERE ts >= ? AND verdict IN "
                                    "('BUY','SELL','EXIT','VETO')", (today,))[0][0],
        "blocked_today": j.db_query("SELECT COUNT(*) FROM decisions WHERE ts >= ? AND verdict='VETO'", (today,))[0][0],
    }

    # --- Vita di una decisione: l'ultima entrata, dal segnale all'esecuzione ---
    life = []
    last_entry = j.rows("SELECT * FROM decisions WHERE verdict IN ('BUY','SELL') ORDER BY ts DESC LIMIT 1")
    if last_entry:
        d = last_entry[0]
        comps = json.loads(d["components"] or "{}")
        life.append({"ts": d["ts"], "tag": "SIGNAL", "text": f"{d['symbol']} {d['verdict']} · score {d['score']:+.0f}"
                     f" · conf {d['confidence']:.0f} · regime {d['regime']}"})
        for k, v in comps.items():
            life.append({"ts": d["ts"], "tag": "INPUT", "text": f"{k} contributo {v:+.1f}"})
        life.append({"ts": d["ts"], "tag": "REASON", "text": d["reason"]})
        life.append({"ts": d["ts"], "tag": "RISK", "text": "risk gate superato: limiti, bracket e orari ok"})
        life.append({"ts": d["ts"], "tag": "BRACKET", "text": f"entrata ~{d['price']:.2f} · stop {d['stop']:.2f}"
                     f" · target {d['take_profit']:.2f}" if d["stop"] and d["take_profit"] else "bracket: —"})
        for o in j.rows("SELECT * FROM orders WHERE symbol=? AND ts>=? ORDER BY ts LIMIT 4", (d["symbol"], d["ts"])):
            life.append({"ts": o["ts"], "tag": "FILL" if o["status"] in ("submitted", "filled") else o["status"].upper(),
                         "text": f"{o['side']} {o['qty']:g} {o['symbol']} · {o['status']}"})
        closed = j.rows("SELECT * FROM closed_trades WHERE symbol=? AND ts>=? ORDER BY ts LIMIT 1", (d["symbol"], d["ts"]))
        if closed:
            c = closed[0]
            life.append({"ts": c["ts"], "tag": "EXIT", "text": f"{c['reason'][:60]} · P/L {c['pnl']:+.2f} $"})
        else:
            life.append({"ts": d["ts"], "tag": "OPEN", "text": "posizione ancora aperta"})
        life_symbol = d["symbol"]
    else:
        life_symbol = None

    # --- Dove atterra: grafico del titolo dell'ultima entrata con entrata, stop e target ---
    charts = j.get("charts", {})
    focus = life_symbol if life_symbol in charts else next(iter(charts), None)
    landing = None
    if focus:
        meta = entries.get(focus) or {}
        dec = last_entry[0] if last_entry and last_entry[0]["symbol"] == focus else {}
        landing = {"symbol": focus, "bars": charts[focus],
                   "entry": meta.get("price") or dec.get("price"), "stop": meta.get("stop") or dec.get("stop"),
                   "take_profit": meta.get("take_profit") or dec.get("take_profit"),
                   "side": "long" if (dec.get("verdict") or "BUY") == "BUY" else "short"}

    # --- Log degli agenti: decisioni, ordini ed eventi mescolati ---
    log = []
    for d in j.rows("SELECT ts, symbol, verdict, confidence, reason, veto FROM decisions "
                    "WHERE verdict NOT IN ('HOLD','SKIP') ORDER BY ts DESC LIMIT 60"):
        log.append({"ts": d["ts"], "tag": d["verdict"], "text": f"{d['symbol']} · {d['veto'] or d['reason']}"[:160]})
    for e in j.rows("SELECT ts, kind, payload FROM events WHERE kind NOT IN ('targets') ORDER BY ts DESC LIMIT 30"):
        p = json.loads(e["payload"])
        text = {"committee": lambda: f"comitato: {((p.get('decision') or {}).get('market_view') or '')[:120]}",
                "fill": lambda: f"{p.get('symbol')} · {p.get('reason')} @ {p.get('price')}",
                "halt": lambda: f"KILL SWITCH · {p.get('reason')}",
                "session_pause": lambda: f"PAUSA DI SESSIONE · {p.get('reason')}",
                "stoploss_guard": lambda: f"StoplossGuard · {p.get('stops')} stop",
                "nightly_review": lambda: "revisione notturna · " + ("; ".join(p.get("changes") or []) or "pesi invariati"),
                "reflection": lambda: f"riflessione su {p.get('trades')} trade"}.get(e["kind"], lambda: e["kind"])()
        log.append({"ts": e["ts"], "tag": e["kind"].upper()[:10], "text": text[:160]})
    log.sort(key=lambda x: x["ts"], reverse=True)

    paused_until = j.get("entries_paused_until")
    cooldowns = {s: u for s, u in j.get("cooldowns", {}).items() if datetime.fromisoformat(u) > now}
    loss_used = max(0.0, -day_ret) / limits.max_daily_loss_pct if limits.max_daily_loss_pct else None
    return {
        "empty": False,
        "demo": bool(j.get("demo")),
        "mode": last["mode"],
        "updated": last["ts"],
        "halted": bool(j.get("halted")),
        "kill_requested": bool(j.get("kill_requested")),
        "session_paused": j.get("paused_session") == day,
        "paused_until": paused_until if paused_until and datetime.fromisoformat(paused_until) > now else None,
        "cooldowns": cooldowns,
        "counters": counters,
        "account": {
            "equity": last["equity"], "cash": last["cash"], "start": first["equity"],
            "day_pnl": last["equity"] - day_start, "day_ret": day_ret,
            "total_ret": last["equity"] / first["equity"] - 1,
            "drawdown": last["equity"] / peak - 1, "max_drawdown": max_dd, "gross": gross,
            "realized": sum(t["pnl"] for t in trades), "loss_used": loss_used,
            "spy_ret": (spy_series[max(spy_series)]["value"] / first["equity"] - 1) if spy_series else None,
            # core + satellite
            "core_enabled": limits.core_enabled,
            "core_symbol": limits.core_symbol if limits.core_enabled else None,
            "core_weight": next((p["weight"] for p in positions if limits.core_enabled
                                 and p["symbol"] == limits.core_symbol), 0.0 if limits.core_enabled else None),
            "satellite_weight": sum(abs(p["weight"]) for p in positions
                                    if not (limits.core_enabled and p["symbol"] == limits.core_symbol)),
            "satellite_pnl": sum(t["pnl"] for t in trades) + sum(
                p["pnl"] for p in positions if not (limits.core_enabled and p["symbol"] == limits.core_symbol)),
        },
        "satellite_halted": bool(j.get("satellite_halted")),
        "satellite_mode": limits.satellite_mode if limits.core_enabled else "live",
        "core_signal": j.get("core_signal"),
        "shadow_positions": j.get("shadow_positions", []),
        "shadow_pnl": sum(r[0] for r in j.db_query("SELECT pnl FROM closed_trades WHERE mode='SHADOW'")),
        "shadow_trades": j.db_query("SELECT COUNT(*) FROM closed_trades WHERE mode='SHADOW'")[0][0],
        "equity": list(series.values()),
        "spy": list(spy_series.values()),
        "drawdown": list(dd_series.values()),
        "positions": sorted(positions, key=lambda p: -abs(p["weight"])),
        "verdicts": stack,
        "observables": observables,
        "life": life,
        "landing": landing,
        "correlations": j.get("correlations"),
        "log": log[:80],
        "strategies": {"stats": by_strategy, "weights": clamp_weights(j.get("weights")),
                       "weights_history": j.get("weights_history", [])},
        "backtest": j.get("last_backtest"),
        "ticker": ticker,
        "market": market,
        "meetings": meetings,
        "trades": trades[:150],
        "stats": {
            "count": len(trades), "win_rate": len(wins) / len(trades) if trades else None,
            "profit_factor": sum(wins) / -sum(losses) if losses else None,
            "avg_win": sum(wins) / len(wins) if wins else None,
            "avg_loss": sum(losses) / len(losses) if losses else None,
            "by_exit": by_exit,
        },
        "orders": j.rows("SELECT ts, symbol, side, qty, reason, status FROM orders ORDER BY ts DESC LIMIT 60"),
        "lessons": j.get("lessons", []),
        "limits": limits.__dict__,
    }


class KillRequest(BaseModel):
    confirm: bool


def create_app(db_path: str | None = None, dashboard_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="PULSE", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                       allow_methods=["GET", "POST"], allow_headers=["*"])
    j = Journal(db_path or os.getenv("DB_PATH", "journal.db"))
    limits = load_settings().risk
    ui = dashboard_dir or DASHBOARD_DIR

    @app.get("/api/state")
    def state():
        return JSONResponse(json.loads(json.dumps(build_state(j, limits), default=str)))

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        """Spinge lo stato solo quando cambia (controllo ogni 2 secondi)."""
        await socket.accept()
        last = None
        try:
            while True:
                payload = json.dumps(build_state(j, limits), default=str)
                digest = hashlib.md5(payload.encode()).hexdigest()
                if digest != last:
                    await socket.send_text(payload)
                    last = digest
                await asyncio.sleep(2)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.post("/api/kill")
    def kill(req: KillRequest):
        if not req.confirm:
            raise HTTPException(400, "Serve la conferma per cancellare gli ordini e chiudere tutte le posizioni.")
        j.set("kill_requested", True)
        j.event("kill_from_app", {})
        return {"ok": True}

    @app.post("/api/kill/cancel")
    def cancel():
        j.set("kill_requested", False)
        return {"ok": True}

    @app.post("/api/resume")
    def resume():
        j.set("halted", False)
        j.set("satellite_halted", False)
        j.set("satellite_peak", None)
        return {"ok": True}

    if (ui / "index.html").exists():
        app.mount("/", StaticFiles(directory=ui, html=True), name="dashboard")
    else:
        @app.get("/")
        def missing():
            return JSONResponse({"error": "Dashboard non ancora compilata: cd dashboard && npm install && npm run build"},
                                status_code=503)
    return app


def serve(port: int = 8000) -> None:
    import uvicorn

    # 127.0.0.1 di default: il command center ha il kill switch e non ha login. Docker usa PULSE_HOST=0.0.0.0
    # ma il Dockerfile pubblica la porta solo sull'host locale.
    uvicorn.run(create_app(), host=os.getenv("PULSE_HOST", "127.0.0.1"), port=port, log_level="warning")
