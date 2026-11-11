"""Dry-run di riconciliazione del criterio 7 (sezione 3 della pre-registrazione).

Calendario fisso di ordini di prova, senza segnale, senza soldi e senza chiavi:
- ogni giorno alle 00:05 UTC un ordine market su BTC/USDC e uno su ETH/USDC, sul dry-run di freqtrade (sede myokx,
  cioè OKX Europe);
- per ogni asset si alterna acquisto e vendita: se non c'è una posizione aperta si compra il 10,4% del capitale,
  altrimenti si vende la stessa quantità comprata;
- per ogni ordine si registrano, in punti base:
  - scarto di esecuzione = prezzo eseguito in dry-run − metà fra bid e ask di OKX Europe all'istante della
    decisione, col segno del costo (positivo = peggio per noi);
  - differenza fra sedi = metà bid/ask di OKX Europe all'istante della decisione − apertura della candela
    giornaliera Coinbase usata dal backtest.

Regola dei giorni saltati, scritta prima del primo ordine:
- un giorno vale se per entrambi gli asset c'è il prezzo OKX all'istante della decisione, l'ordine parte entro
  DRYRUN_MAX_DELAY_S secondi dalle 00:05 UTC, il dry-run lo esegue e l'apertura Coinbase del giorno esiste;
- un giorno che non vale si registra con la causa e si recupera in coda: il calendario si allunga di un giorno;
- al quarto giorno non valido il dry-run fallisce, si corregge la causa e si riparte da zero con una nuova data.

PULSE parla con freqtrade solo via REST (confine GPL): qui non si importa niente da freqtrade.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import config, data, live

DIR = live.LIVE_DIR / "dryrun"
START = DIR / "start.json"
LOG = DIR / "orders.jsonl"
FT_DIR = config.ROOT / "freqtrade"
FT_FILES = [FT_DIR / "config.dryrun.json", FT_DIR / "user_data" / "strategies" / "NoSignal.py",
            FT_DIR / "requirements.lock"]
PLAN_FILES = [Path(__file__), Path(config.__file__), Path(live.__file__)] + FT_FILES
COINBASE_DAY = "https://api.exchange.coinbase.com/products/{p}/candles?granularity=86400&start={s}&end={s}"


# ------------------------------------------------------------ piano e impronta

def plan_fingerprint() -> str:
    lines = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(config.ROOT)}\n"
                    for p in PLAN_FILES)
    return hashlib.sha256(lines.encode()).hexdigest()[:16]


def plan(start: date) -> dict:
    return {"start": start.isoformat(), "valid_days_needed": config.DRYRUN_DAYS,
            "last_day_max": (start + timedelta(days=config.DRYRUN_DAYS + config.DRYRUN_MAX_MISSED - 1)).isoformat(),
            "time_utc": "%02d:%02d" % config.DRYRUN_TIME_UTC, "max_delay_s": config.DRYRUN_MAX_DELAY_S,
            "max_missed": config.DRYRUN_MAX_MISSED, "size_frac": config.DRYRUN_SIZE_FRAC,
            "stake_usdc": stake(), "capital_usdc": config.DRYRUN_CAPITAL, "pairs": config.DRYRUN_PAIRS,
            "freqtrade": config.FREQTRADE_VERSION, "fingerprint": plan_fingerprint()}


def stake() -> float:
    return round(config.DRYRUN_SIZE_FRAC * config.DRYRUN_CAPITAL, 2)


def start(day: str, today: date | None = None, path: Path = START) -> dict:
    """Scrive data d'inizio e impronta prima del primo ordine. Non sovrascrive un dry-run già iniziato."""
    d = date.fromisoformat(day)
    today = today or datetime.now(timezone.utc).date()
    if d < config.LIVE_START.date():
        raise PermissionError(f"Il dry-run usa solo date dal {config.LIVE_START.date()} in poi")
    if d <= today:
        raise ValueError("La data d'inizio va scritta prima: deve essere almeno domani (UTC)")
    if path.exists():
        raise FileExistsError(f"Dry-run già pianificato in {path}: per ripartire va archiviato a mano")
    path.parent.mkdir(parents=True, exist_ok=True)
    p = plan(d)
    path.write_text(json.dumps(p, indent=2) + "\n")
    return p


def load_start(path: Path = START) -> dict:
    if not path.exists():
        raise FileNotFoundError("Dry-run non pianificato: python -m pulse_mm.research.crypto_trend dryrun start AAAA-MM-GG")
    return json.loads(path.read_text())


# ------------------------------------------------------------ prezzi

def http_json(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"User-Agent": "pulse-research/1.0", "Content-Type": "application/json",
                                          **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def okx_quote(asset: str, get=http_json) -> dict:
    """Bid e ask di OKX Europe dall'API pubblica. Solleva un errore se mancano."""
    d = get(config.DRYRUN_OKX_TICKER.format(i=config.DRYRUN_OKX_INST[asset]))["data"][0]
    bid, ask = float(d["bidPx"]), float(d["askPx"])
    ts = datetime.fromtimestamp(int(d["ts"]) / 1000, tz=timezone.utc)
    live.check_dates([pd.Timestamp(ts).tz_localize(None)])
    if not (bid > 0 and ask >= bid):
        raise ValueError(f"Quotazione OKX non valida: {bid} / {ask}")
    return {"bid": bid, "ask": ask, "mid": (bid + ask) / 2, "ts": ts.isoformat()}


def coinbase_open(asset: str, day: date, get=data.http_get) -> float | None:
    """Apertura della candela giornaliera Coinbase del giorno (00:00 UTC), dal flusso dal vivo."""
    s = f"{day.isoformat()}T00:00:00Z"
    rows = json.loads(get(COINBASE_DAY.format(p=asset, s=s)))
    bars = data.parse(json.dumps(rows).encode())
    live.LiveFeed(fetch=None).bars(bars)                      # rifiuta date prima del 2026-11-01
    hit = bars[bars.index == pd.Timestamp(day)]
    return float(hit["open"].iloc[0]) if len(hit) else None


def okx_book(asset: str, get=http_json) -> dict:
    """Fotografia dei primi 400 livelli del book di OKX Europe: [[prezzo, quantità], ...] per lato."""
    d = get(config.DRYRUN_OKX_BOOK.format(i=config.DRYRUN_OKX_INST[asset]))["data"][0]
    side = lambda xs: [[float(x[0]), float(x[1])] for x in xs]
    return {"bids": side(d["bids"]), "asks": side(d["asks"]),
            "ts": datetime.fromtimestamp(int(d["ts"]) / 1000, tz=timezone.utc).isoformat()}


def walk_cost_bp(book: dict, side: str, notional: float, mid: float) -> float | None:
    """Costo rispetto al prezzo medio, col segno del costo, per un ordine market di `notional` USDC sul book.
    None se il book fotografato non basta a riempire l'ordine."""
    levels = book["asks"] if side == "buy" else book["bids"]
    left, qty = notional, 0.0
    for px, sz in levels:
        take = min(left, px * sz)
        qty += take / px
        left -= take
        if left <= 1e-9:
            vwap = notional / qty
            return (vwap - mid) / mid * 1e4 if side == "buy" else (mid - vwap) / mid * 1e4
    return None


def depth_costs(book: dict, side: str, mid: float) -> dict:
    return {f"x{m}": walk_cost_bp(book, side, stake() * m, mid) for m in config.DRYRUN_DEPTH_MULTS}


# ------------------------------------------------------------ freqtrade via REST

class Freqtrade:
    """Client REST minimo per il dry-run di freqtrade in un processo separato."""

    def __init__(self, user: str, password: str, base: str = config.FREQTRADE_API, call=http_json):
        self.base, self.call = base, call
        basic = base64.b64encode(f"{user}:{password}".encode()).decode()
        tok = call(f"{base}/token/login", method="POST", body={}, headers={"Authorization": f"Basic {basic}"})
        self.auth = {"Authorization": f"Bearer {tok['access_token']}"}

    def _get(self, path):
        return self.call(f"{self.base}{path}", headers=self.auth)

    def _post(self, path, body):
        return self.call(f"{self.base}{path}", method="POST", body=body, headers=self.auth)

    def show_config(self) -> dict:
        return self._get("/show_config")

    def open_trade(self, pair: str) -> dict | None:
        return next((t for t in self._get("/status") if t["pair"] == pair), None)

    def trade(self, trade_id: int) -> dict:
        return self._get(f"/trade/{trade_id}")

    def buy(self, pair: str, stake_usdc: float) -> dict:
        return self._post("/forceenter", {"pair": pair, "side": "long", "ordertype": "market",
                                          "stakeamount": stake_usdc, "entry_tag": "pulse-ct-dryrun"})

    def sell(self, trade_id: int) -> dict:
        return self._post("/forceexit", {"tradeid": str(trade_id), "ordertype": "market"})


def fill_price(trade: dict, side: str) -> float | None:
    """Prezzo eseguito dell'ultimo ordine del lato richiesto, se è stato riempito."""
    want = "buy" if side == "buy" else "sell"
    for o in reversed(trade.get("orders", [])):
        if o.get("ft_order_side") == want and (o.get("filled") or 0) > 0:
            return float(o.get("safe_price") or o.get("average") or o["price"])
    return None


def check_venue(ft: Freqtrade) -> None:
    cfg = ft.show_config()
    if not cfg.get("dry_run") or cfg.get("exchange") != "myokx":
        raise PermissionError(f"freqtrade deve essere in dry-run su myokx: dry_run={cfg.get('dry_run')}, "
                              f"exchange={cfg.get('exchange')}")


# ------------------------------------------------------------ un giorno del calendario

def decision_time(day: date) -> datetime:
    h, m = config.DRYRUN_TIME_UTC
    return datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)


def rows(path: Path = LOG) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _append(row: dict, path: Path = LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def tick(ft: Freqtrade | None, now: datetime | None = None, quote=okx_quote, cb_open=coinbase_open,
         start_path: Path = START, log: Path = LOG, wait_fill_s: float = 30.0, book=okx_book) -> list[dict]:
    """Esegue gli ordini del giorno. Idempotente: un giorno già registrato non si ripete."""
    p = load_start(start_path)
    if plan_fingerprint() != p["fingerprint"]:
        raise PermissionError("Codice o config del dry-run cambiati dopo l'inizio: il dry-run non vale più")
    now = now or datetime.now(timezone.utc)
    day = now.date()
    if day < date.fromisoformat(p["start"]) or day > date.fromisoformat(p["last_day_max"]):
        return []
    if any(r["day"] == day.isoformat() for r in rows(log)):
        return []
    delay = (now - decision_time(day)).total_seconds()
    out = []
    if not 0 <= delay <= config.DRYRUN_MAX_DELAY_S:
        r = {"day": day.isoformat(), "asset": None, "status": "late", "delay_s": round(delay, 1)}
        _append(r, log)
        return [r]
    for asset, pair in config.DRYRUN_PAIRS.items():
        r = {"day": day.isoformat(), "asset": asset, "pair": pair, "t_decision": now.isoformat(),
             "delay_s": round(delay, 1)}
        try:
            r["okx"] = quote(asset)
        except Exception as e:                              # prezzo OKX mancante: niente ordine
            r.update(status="okx_price_missing", error=str(e)[:200])
            _append(r, log); out.append(r)
            continue
        try:                                                # fotografia del book: utile, non decide la validità
            r["book"] = book(asset)
        except Exception as e:
            r["book"], r["book_error"] = None, str(e)[:200]
        try:
            if ft is None:
                raise ConnectionError("freqtrade non raggiungibile")
            check_venue(ft)
            open_t = ft.open_trade(pair)
            r["side"] = "sell" if open_t else "buy"
            res = ft.buy(pair, stake()) if r["side"] == "buy" else ft.sell(open_t["trade_id"])
            tid = res.get("trade_id") or (open_t or {}).get("trade_id")
            r["trade_id"] = tid
            px, waited = None, 0.0
            while px is None and waited <= wait_fill_s:
                px = fill_price(ft.trade(tid), r["side"])
                if px is None:
                    time.sleep(1.0); waited += 1.0
            if px is None:
                r["status"] = "not_filled"
            else:
                r["fill"] = px
                r["status"] = "ok"
        except Exception as e:
            r.update(status="order_failed", error=str(e)[:200])
        try:
            r["coinbase_open"] = cb_open(asset, day)
        except Exception as e:
            r["coinbase_open"] = None
            r["coinbase_error"] = str(e)[:200]
        _append(r, log); out.append(r)
    return out


def fill_coinbase(cb_open=coinbase_open, log: Path = LOG) -> int:
    """Riprova l'apertura Coinbase mancante (la candela del giorno esiste dalle 00:00 UTC)."""
    rs, n = rows(log), 0
    for r in rs:
        if r.get("asset") and r.get("coinbase_open") is None:
            try:
                r["coinbase_open"] = cb_open(r["asset"], date.fromisoformat(r["day"]))
                n += r["coinbase_open"] is not None
            except Exception:
                pass
    if n:
        log.write_text("".join(json.dumps(r) + "\n" for r in rs))
    return n


# ------------------------------------------------------------ misure e controllo giornaliero

def measures(r: dict) -> dict | None:
    if r.get("status") != "ok" or not r.get("okx") or not r.get("fill"):
        return None
    mid, fill, sign = r["okx"]["mid"], r["fill"], (1 if r["side"] == "buy" else -1)
    out = {"exec_gap_bp": sign * (fill - mid) / mid * 1e4, "venue_basis_bp": None, "venue_cost_bp": None,
           "spread_bp": (r["okx"]["ask"] - r["okx"]["bid"]) / mid * 1e4,
           "depth_bp": depth_costs(r["book"], r["side"], mid) if r.get("book") else None}
    if r.get("coinbase_open"):
        cb = r["coinbase_open"]
        out["venue_basis_bp"] = (mid - cb) / cb * 1e4
        out["venue_cost_bp"] = sign * out["venue_basis_bp"]
    return out


def day_status(day_rows: list[dict]) -> tuple[bool, list[str]]:
    issues = []
    if not day_rows:
        return False, ["ordine non partito: nessuna riga per il giorno"]
    for r in day_rows:
        if r.get("status") == "late":
            issues.append(f"esecuzione in ritardo di {r['delay_s']} s")
            continue
        if r.get("status") == "okx_price_missing":
            issues.append(f"{r['asset']}: prezzo OKX mancante all'istante della decisione")
        elif r.get("status") != "ok":
            issues.append(f"{r['asset']}: ordine non eseguito ({r.get('status')})")
        if r.get("asset") and r.get("coinbase_open") is None:
            issues.append(f"{r['asset']}: apertura Coinbase mancante")
    assets = {r.get("asset") for r in day_rows}
    for a in config.DRYRUN_PAIRS:
        if a not in assets and not issues:
            issues.append(f"{a}: nessuna riga")
    return not issues, issues


def check(now: datetime | None = None, start_path: Path = START, log: Path = LOG) -> dict:
    """Controllo giornaliero: segnala ordini non partiti e prezzi OKX mancanti, conta i giorni validi."""
    p = load_start(start_path)
    now = now or datetime.now(timezone.utc)
    d0, last = date.fromisoformat(p["start"]), date.fromisoformat(p["last_day_max"])
    by_day: dict[str, list] = {}
    for r in rows(log):
        by_day.setdefault(r["day"], []).append(r)
    days, valid, missed = [], 0, 0
    d = d0
    while d <= last and valid < config.DRYRUN_DAYS and missed <= config.DRYRUN_MAX_MISSED:
        if now < decision_time(d) + timedelta(seconds=config.DRYRUN_MAX_DELAY_S + 60):
            break                                           # giorno non ancora dovuto
        ok, issues = day_status(by_day.get(d.isoformat(), []))
        valid += ok
        missed += not ok
        days.append({"day": d.isoformat(), "ok": ok, "issues": issues})
        d += timedelta(days=1)
    if missed > config.DRYRUN_MAX_MISSED:
        state = "fallito: oltre 3 giorni non validi, si corregge la causa e si riparte da zero"
    elif valid >= config.DRYRUN_DAYS:
        state = "completo"
    else:
        state = "in corso"
    return {"start": p["start"], "valid_days": valid, "missed_days": missed, "state": state,
            "alerts": [x for x in days if not x["ok"]], "last_checked": days[-1]["day"] if days else None}


def coinbase_returns(asset: str, start: date, end: date, get=data.http_get) -> pd.Series:
    """Rendimenti giornalieri Coinbase, chiusura su chiusura, dal flusso dal vivo (date dal 2026-11-01)."""
    s0 = (start - timedelta(days=1)).isoformat()
    url = (f"https://api.exchange.coinbase.com/products/{asset}/candles?granularity=86400"
           f"&start={s0}T00:00:00Z&end={end.isoformat()}T00:00:00Z")
    bars = live.LiveFeed(fetch=None).bars(data.parse(get(url)))
    r = bars["close"].pct_change().dropna()
    return r[(r.index >= pd.Timestamp(start)) & (r.index <= pd.Timestamp(end))]


def stress(rs: list[dict], returns: dict[str, pd.Series]) -> dict:
    """Giorni agitati del dry-run secondo la definizione scritta prima di iniziare (revisione 3b)."""
    days = sorted({r["day"] for r in rs if r.get("asset")})
    hit = {}
    for d in days:
        why = []
        for a, lim in config.DRYRUN_STRESS_ABS_RET.items():
            x = returns.get(a, pd.Series(dtype=float)).get(pd.Timestamp(d))
            if x is not None and abs(x) >= lim:
                why.append(f"{a} {x:+.1%}")
        for r in rs:
            if r["day"] == d and r.get("okx"):
                sp = (r["okx"]["ask"] - r["okx"]["bid"]) / r["okx"]["mid"] * 1e4
                if sp >= config.DRYRUN_STRESS_SPREAD_BP:
                    why.append(f"{r['asset']} spread {sp:.1f} bp")
        if why:
            hit[d] = why
    return {"days": len(days), "stress_days": hit,
            "limit": None if hit else "nessun giorno agitato nei giorni del dry-run: il risultato vale per giorni calmi"}


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def report(log: Path = LOG, returns: dict[str, pd.Series] | None = None) -> dict:
    """Esito del criterio 7, solo a dry-run completo. Verifica la catena e la differenza fra sedi; sullo slippage
    è un limite basso dei costi e può fallire solo in casi estremi (revisione 3b)."""
    rs = rows(log)
    m = [x for x in (measures(r) for r in rs) if x]
    if not m:
        return {"orders": 0}
    gap = [x["exec_gap_bp"] for x in m]
    mean_gap = sum(gap) / len(gap)
    depth = {}
    for k in (f"x{q}" for q in config.DRYRUN_DEPTH_MULTS):
        v = [x["depth_bp"][k] if x["depth_bp"] else None for x in m]
        ok = [y for y in v if y is not None]
        depth[k] = {"mean_bp": _avg(ok), "max_bp": max(ok) if ok else None,
                    "book_too_thin": sum(1 for x in m if x["depth_bp"] and x["depth_bp"][k] is None),
                    "no_snapshot": sum(1 for x in m if not x["depth_bp"])}
    sp = [x["spread_bp"] for x in m]
    return {"orders": len(m), "exec_gap_bp_mean": mean_gap, "exec_gap_bp_max": max(gap),
            "venue_basis_bp_mean": _avg([x["venue_basis_bp"] for x in m]),
            "venue_cost_bp_mean": _avg([x["venue_cost_bp"] for x in m]),
            "spread_bp_mean": sum(sp) / len(sp), "spread_bp_max": max(sp),
            "depth_cost_by_size": depth,
            "stress": stress(rs, returns) if returns is not None else "non calcolato",
            "assumed_spread_plus_slippage_bp": config.DRYRUN_COST_BP,
            "costs_hold": mean_gap <= config.DRYRUN_COST_BP,
            "note": "verifica la catena e la differenza fra sedi; limite basso dei costi, ordini simulati sul book"}


# ------------------------------------------------------------ prova di collegamento (non conta)

def smoke(ft: Freqtrade, quote=okx_quote, path: Path = DIR / "smoke.jsonl", wait_fill_s: float = 30.0,
          book=okx_book) -> list[dict]:
    """Un acquisto e una vendita per asset, subito, per provare il collegamento. Non entra nel conteggio."""
    check_venue(ft)
    out = []
    for asset, pair in config.DRYRUN_PAIRS.items():
        for side in ("buy", "sell"):
            r = {"day": datetime.now(timezone.utc).date().isoformat(), "asset": asset, "pair": pair, "side": side,
                 "smoke": True, "okx": quote(asset), "book": book(asset)}
            open_t = ft.open_trade(pair)
            if side == "buy" and open_t:
                raise RuntimeError(f"{pair}: posizione già aperta, la prova parte solo da zero")
            res = ft.buy(pair, stake()) if side == "buy" else ft.sell(open_t["trade_id"])
            tid = res.get("trade_id") or (open_t or {}).get("trade_id")
            px, waited = None, 0.0
            while px is None and waited <= wait_fill_s:
                px = fill_price(ft.trade(tid), side)
                if px is None:
                    time.sleep(1.0); waited += 1.0
            r.update(trade_id=tid, fill=px, status="ok" if px else "not_filled")
            r["measures"] = measures(r)
            _append(r, path)
            out.append(r)
    return out


def client_from_env(env: Path = FT_DIR / ".env") -> Freqtrade:
    vals = dict(line.split("=", 1) for line in env.read_text().splitlines() if "=" in line)
    return Freqtrade(vals["FREQTRADE__API_SERVER__USERNAME"], vals["FREQTRADE__API_SERVER__PASSWORD"])


def client_or_none() -> Freqtrade | None:
    try:
        return client_from_env()
    except Exception:
        return None
