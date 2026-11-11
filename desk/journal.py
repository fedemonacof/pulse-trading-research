"""Diario SQLite: ogni decisione, report, ordine ed equity resta registrato e verificabile.

Un lock serializza l'accesso: il motore, il thread Telegram e l'app condividono la stessa connessione.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Colonne aggiunte dopo la prima versione: i diari vecchi vengono aggiornati all'apertura
MIGRATIONS = {
    "closed_trades": {"regime": "TEXT", "strategy": "TEXT", "confidence": "REAL", "entry_ts": "TEXT",
                      "holding_minutes": "REAL"},
    "equity": {"spy": "REAL"},
}


class Journal:
    def __init__(self, path: str, clock=_utcnow):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self.clock = clock  # iniettabile: il simulatore registra giorni finti
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (ts TEXT, kind TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS equity (ts TEXT, mode TEXT, equity REAL, cash REAL);
            CREATE TABLE IF NOT EXISTS orders (ts TEXT, mode TEXT, symbol TEXT, side TEXT, qty REAL,
                                               reason TEXT, order_id TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS closed_trades (ts TEXT, mode TEXT, symbol TEXT, direction TEXT,
                                               qty REAL, entry REAL, exit REAL, pnl REAL, pnl_pct REAL,
                                               reason TEXT, thesis TEXT, reflected INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS decisions (ts TEXT, symbol TEXT, action TEXT, intent TEXT, verdict TEXT,
                                               confidence REAL, score REAL, regime TEXT, strategy TEXT,
                                               reason TEXT, veto TEXT, price REAL, stop REAL, take_profit REAL,
                                               components TEXT);
            CREATE TABLE IF NOT EXISTS observables (ts TEXT, payload TEXT);
            -- Dati grezzi per la valutazione in avanti (docs/preregistrazione-avanti.md): voti del comitato anche
            -- sotto la soglia di confidenza, e punteggi delle strategie NON pesati.
            CREATE TABLE IF NOT EXISTS votes (ts TEXT, symbol TEXT, target_weight REAL, confidence REAL,
                                              conviction REAL, price REAL, model TEXT);
            CREATE TABLE IF NOT EXISTS signals (ts TEXT, symbol TEXT, price REAL, trend_score REAL, mr_score REAL);
            CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
            CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity(ts);
            """
        )
        for table, cols in MIGRATIONS.items():
            have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for col, typ in cols.items():
                if col not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        self.db.commit()

    def _write(self, sql: str, params=()) -> None:
        with self._lock:
            self.db.execute(sql, params)
            self.db.commit()

    def now(self) -> str:
        return self.clock().isoformat(timespec="seconds")

    def db_query(self, sql: str, params=()) -> list[tuple]:
        with self._lock:
            return self.db.execute(sql, params).fetchall()

    def rows(self, sql: str, params=()) -> list[dict]:
        with self._lock:
            cur = self.db.execute(sql, params)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def closed_trade(self, mode: str, t: dict) -> None:
        self._write(
            "INSERT INTO closed_trades (ts, mode, symbol, direction, qty, entry, exit, pnl, pnl_pct, reason, thesis,"
            " regime, strategy, confidence, entry_ts, holding_minutes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.now(), mode, t["symbol"], t["direction"], t["qty"], t["entry"], t["exit"], t["pnl"], t["pnl_pct"],
             t["reason"], t.get("thesis", ""), t.get("regime"), t.get("strategy"), t.get("confidence"),
             t.get("entry_ts"), t.get("holding_minutes")),
        )

    def unreflected_trades(self) -> list[dict]:
        return self.rows("SELECT rowid, * FROM closed_trades WHERE reflected=0 ORDER BY ts")

    def mark_reflected(self, rowids: list[int]) -> None:
        with self._lock:
            self.db.executemany("UPDATE closed_trades SET reflected=1 WHERE rowid=?", [(r,) for r in rowids])
            self.db.commit()

    def event(self, kind: str, payload) -> None:
        self._write("INSERT INTO events VALUES (?,?,?)", (self.now(), kind, json.dumps(payload, default=str)))

    def equity(self, mode: str, equity: float, cash: float, spy: float | None = None) -> None:
        self._write("INSERT INTO equity (ts, mode, equity, cash, spy) VALUES (?,?,?,?,?)",
                    (self.now(), mode, equity, cash, spy))

    def order(self, mode, symbol, side, qty, reason, order_id, status) -> None:
        self._write("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
                    (self.now(), mode, symbol, side, qty, reason, order_id, status))

    def decision(self, d: dict, verdict: str, veto: str | None = None) -> None:
        """verdict: BUY / SELL / EXIT / HOLD / SKIP / VETO, come nella pila dei verdetti della dashboard."""
        self._write(
            "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.now(), d["symbol"], d["action"], d["intent"], verdict, d["confidence"], d["score"], d["regime"],
             d["strategy"], d["reason"], veto, d.get("price"), d.get("stop"), d.get("take_profit"),
             json.dumps(d.get("components") or {})),
        )

    def vote(self, symbol: str, target_weight: float, confidence: float, conviction: float,
             price: float | None, model: str) -> None:
        self._write("INSERT INTO votes VALUES (?,?,?,?,?,?,?)",
                    (self.now(), symbol, target_weight, confidence, conviction, price, model))

    def signals(self, rows: list[tuple]) -> None:
        """rows: (symbol, price, trend_score, mr_score)."""
        ts = self.now()
        with self._lock:
            self.db.executemany("INSERT INTO signals VALUES (?,?,?,?,?)", [(ts, *r) for r in rows])
            self.db.commit()

    def observables(self, payload: dict) -> None:
        self._write("INSERT INTO observables VALUES (?,?)", (self.now(), json.dumps(payload, default=str)))

    def trades_today(self) -> int:
        today = self.clock().date().isoformat()
        return self.db_query("SELECT COUNT(*) FROM orders WHERE ts >= ? AND status='submitted'", (today,))[0][0]

    def get(self, key: str, default=None):
        rows = self.db_query("SELECT value FROM state WHERE key=?", (key,))
        return json.loads(rows[0][0]) if rows else default

    def set(self, key: str, value) -> None:
        self._write("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value, default=str)))
