"""Dati di mercato gratuiti, senza chiavi: le stesse fonti pubbliche usate da OpenTerminal
(https://github.com/ErTasselli/OpenTerminal, licenza MIT), riscritte in Python.

    Notizie        Yahoo Finance RSS per titolo  -> fallback Google News RSS
    Macro          FRED (Fed di St. Louis): tassi a 3 mesi, 2 e 10 anni, Fed funds, VIX
    Calendario     Forex Factory: eventi macro di questa e della prossima settimana
    Fondamentali   scanner pubblico di TradingView: P/E, capitalizzazione, settore, beta,
                   data della prossima trimestrale e stima dell'EPS

Sono endpoint pubblici ma non ufficiali: i dati vanno considerati indicativi. Ogni fonte
è isolata: se una non risponde, le altre continuano e il comitato riceve una nota.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .data import NewsItem

log = logging.getLogger("desk.freedata")

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
CLIENT_UA = "trading-desk/1.0 (+https://github.com/ErTasselli/OpenTerminal)"  # FRED rifiuta gli UA da browser senza header

FRED_SERIES = {
    "DGS3MO": "Treasury 3 mesi",
    "DGS2": "Treasury 2 anni",
    "DGS10": "Treasury 10 anni",
    "DFF": "Fed funds effettivo",
    "VIXCLS": "VIX",
}
TV_COLUMNS = [
    "earnings_release_next_date", "earnings_per_share_forecast_next_fq", "price_earnings_ttm",
    "market_cap_basic", "sector", "beta_1_year", "dividends_yield_current",
]


class FreeData:
    def __init__(self, timeout: float = 15.0, ttl_seconds: int = 600, fetch=None):
        self.timeout = timeout
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, object]] = {}
        self._fetch = fetch or self._http   # iniettabile nei test

    # ---------- HTTP con cache ----------

    def _http(self, url: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
        req = urllib.request.Request(url, data=data, headers=headers or {})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read()

    def _cached(self, key: str, fn):
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        value = fn()
        self._cache[key] = (time.monotonic(), value)
        return value

    # ---------- Notizie ----------

    @staticmethod
    def _parse_rss(xml: bytes, source: str, symbol: str | None) -> list[NewsItem]:
        root = ET.fromstring(xml)
        out = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            if not title:
                continue
            try:
                when = parsedate_to_datetime(it.findtext("pubDate") or "")
            except (TypeError, ValueError):
                when = datetime.now(timezone.utc)
            src = it.find("source")
            summary = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
            out.append(NewsItem(
                created_at=when, headline=title, summary=" ".join(summary.split())[:400],
                source=(src.text if src is not None and src.text else source),
                symbols=[symbol] if symbol else [],
            ))
        return out

    def _symbol_news(self, symbol: str) -> list[NewsItem]:
        def yahoo():
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={urllib.parse.quote(symbol)}&region=US&lang=en-US"
            return self._parse_rss(self._fetch(url, None, {"User-Agent": BROWSER_UA}), "Yahoo Finance", symbol)

        def google():
            q = urllib.parse.quote(f"{symbol} stock")
            url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
            return self._parse_rss(self._fetch(url, None, {"User-Agent": BROWSER_UA}), "Google News", symbol)

        try:
            items = yahoo()
            if items:
                return items
        except Exception as e:
            log.info("Yahoo RSS non disponibile per %s (%s): provo Google News", symbol, e)
        return google()

    def news(self, symbols: list[str], hours: int = 48, per_symbol: int = 8) -> list[NewsItem]:
        def load():
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            with ThreadPoolExecutor(max_workers=6) as pool:
                lists = list(pool.map(self._safe_symbol_news, symbols))
            return dedupe([[n for n in lst if n.created_at >= since][:per_symbol] for lst in lists])

        return self._cached(f"news:{','.join(symbols)}:{hours}", load)

    def _safe_symbol_news(self, symbol: str) -> list[NewsItem]:
        try:
            return self._symbol_news(symbol)
        except Exception as e:
            log.warning("Notizie non disponibili per %s: %s", symbol, e)
            return []

    # ---------- Macro (FRED) ----------

    def _fred(self, series_id: str) -> list[tuple[str, float]]:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        text = self._fetch(url, None, {"User-Agent": CLIENT_UA}).decode()
        points = []
        for line in text.strip().splitlines()[1:]:
            date, _, raw = line.partition(",")
            try:
                points.append((date, float(raw)))
            except ValueError:
                continue  # FRED usa "." per i giorni senza dato
        return points[-260:]

    def macro(self) -> dict:
        def load():
            out = {}
            for sid, name in FRED_SERIES.items():
                try:
                    pts = self._fred(sid)
                    last_date, last = pts[-1]
                    week = pts[-6][1] if len(pts) > 5 else None
                    month = pts[-22][1] if len(pts) > 21 else None
                    out[sid] = {
                        "nome": name, "valore": last, "data": last_date,
                        "var_1s": round(last - week, 3) if week is not None else None,
                        "var_1m": round(last - month, 3) if month is not None else None,
                    }
                except Exception as e:
                    out[sid] = {"nome": name, "errore": str(e)[:120]}
            if "valore" in out.get("DGS10", {}) and "valore" in out.get("DGS2", {}):
                out["curva_10a_2a"] = round(out["DGS10"]["valore"] - out["DGS2"]["valore"], 3)
            return out

        return self._cached("macro", load)

    # ---------- Calendario macro (Forex Factory) ----------

    def calendar(self, days: int = 7, countries=("USD", "EUR"), impacts=("High", "Medium")) -> list[dict]:
        def load():
            now = datetime.now(timezone.utc)
            events = []
            for week in ("thisweek", "nextweek"):
                try:
                    raw = json.loads(self._fetch(f"https://nfs.faireconomy.media/ff_calendar_{week}.json",
                                                 None, {"User-Agent": BROWSER_UA}))
                except Exception as e:
                    log.info("Calendario %s non disponibile: %s", week, e)
                    continue
                for ev in raw:
                    try:
                        when = datetime.fromisoformat(ev["date"]).astimezone(timezone.utc)
                    except (KeyError, ValueError):
                        continue
                    if ev.get("country") not in countries or ev.get("impact") not in impacts:
                        continue
                    if not (now - timedelta(hours=12) <= when <= now + timedelta(days=days)):
                        continue
                    events.append({
                        "quando": when.isoformat(timespec="minutes"), "paese": ev["country"],
                        "evento": ev.get("title", ""), "impatto": ev["impact"],
                        "previsione": ev.get("forecast") or None, "precedente": ev.get("previous") or None,
                    })
            seen, out = set(), []
            for e in sorted(events, key=lambda e: e["quando"]):
                k = (e["quando"], e["evento"])
                if k not in seen:
                    seen.add(k)
                    out.append(e)
            return out

        return self._cached(f"calendar:{days}", load)

    # ---------- Fondamentali e trimestrali (TradingView scanner) ----------

    def fundamentals(self, symbols: list[str]) -> dict[str, dict]:
        def load():
            # L'exchange non è noto: si chiede ogni titolo su tutti e tre, TradingView scarta quelli sbagliati
            tickers = [f"{ex}:{s}" for s in symbols for ex in ("NASDAQ", "NYSE", "AMEX")]
            body = json.dumps({"symbols": {"tickers": tickers}, "columns": TV_COLUMNS}).encode()
            raw = json.loads(self._fetch("https://scanner.tradingview.com/america/scan", body, {
                "User-Agent": BROWSER_UA, "Content-Type": "application/json",
                "Referer": "https://www.tradingview.com/", "Origin": "https://www.tradingview.com",
            }))
            out: dict[str, dict] = {}
            now = datetime.now(timezone.utc)
            for row in raw.get("data", []):
                sym = row["s"].split(":")[1]
                if sym in out:
                    continue
                d = dict(zip(TV_COLUMNS, row["d"]))
                nxt = d["earnings_release_next_date"]
                when = datetime.fromtimestamp(nxt, timezone.utc) if nxt else None
                out[sym] = {
                    "prossima_trimestrale": when.date().isoformat() if when else None,
                    "giorni_alla_trimestrale": (when - now).days if when and when > now else None,
                    "eps_stimato_prossimo_trim": d["earnings_per_share_forecast_next_fq"],
                    "pe_ttm": round(d["price_earnings_ttm"], 1) if d["price_earnings_ttm"] else None,
                    "capitalizzazione_mld": round(d["market_cap_basic"] / 1e9, 1) if d["market_cap_basic"] else None,
                    "settore": d["sector"],
                    "beta_1a": round(d["beta_1_year"], 2) if d["beta_1_year"] else None,
                    "dividendo_pct": round(d["dividends_yield_current"], 2) if d["dividends_yield_current"] else None,
                }
            return out

        return self._cached(f"fund:{','.join(symbols)}", load)

    # ---------- Tutto insieme ----------

    def briefing(self, symbols: list[str]) -> dict:
        """Dati per il comitato. Una fonte che fallisce lascia una nota, non blocca le altre."""
        out: dict = {"fonti_non_disponibili": []}
        tasks = {
            "macro": self.macro,
            "calendario": lambda: self.calendar(),
            "fondamentali": lambda: self.fundamentals(symbols),
            "notizie": lambda: self.news(symbols),
        }
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {k: pool.submit(fn) for k, fn in tasks.items()}
            for k, f in futures.items():
                try:
                    out[k] = f.result()
                except Exception as e:
                    log.warning("Fonte %s non disponibile: %s", k, e)
                    out[k] = [] if k in ("calendario", "notizie") else {}
                    out["fonti_non_disponibili"].append(k)
        return out


def dedupe(lists: list[list[NewsItem]]) -> list[NewsItem]:
    """Unisce, elimina i doppioni per titolo normalizzato, dal più recente."""
    seen, out = set(), []
    for item in (n for lst in lists for n in lst):
        key = re.sub(r"[^a-z0-9]+", " ", item.headline.lower()).strip()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return sorted(out, key=lambda n: n.created_at, reverse=True)
