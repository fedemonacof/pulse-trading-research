"""Monitor live nel terminale (sola lettura del diario): python main.py monitor"""
from __future__ import annotations

import json
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .journal import Journal


def _pct(x: float) -> Text:
    return Text(f"{x:+.2%}", style="green" if x >= 0 else "red")


def render(j: Journal) -> Group:
    eq = j.db_query("SELECT ts, mode, equity FROM equity WHERE mode != 'SHADOW' ORDER BY ts DESC LIMIT 1")
    first_today = j.db_query("SELECT equity FROM equity WHERE mode != 'SHADOW' AND ts >= date('now') ORDER BY ts LIMIT 1")
    peak = j.get("equity_peak", 0) or 0
    head = Table.grid(expand=True)
    for _ in range(5):
        head.add_column()
    if eq:
        ts, mode, equity = eq[0]
        today = equity / first_today[0][0] - 1 if first_today else 0.0
        dd = equity / peak - 1 if peak else 0.0
        status = "[red]FERMO[/]" if j.get("halted") else "[green]ATTIVO[/]"
        head.add_row(f"[bold]{mode}[/] {status}", f"Equity [bold]{equity:,.0f} $[/]",
                     Text.assemble("Oggi ", _pct(today)), Text.assemble("Drawdown ", _pct(dd)), f"agg. {ts[11:19]} UTC")
    else:
        head.add_row("Nessun dato: avvia `python main.py run`", "", "", "", "")

    pos = Table(title="Posizioni", expand=True)
    for c in ("Titolo", "Qty", "Carico", "Prezzo", "P/L %", "Picco"):
        pos.add_column(c, justify="right" if c != "Titolo" else "left")
    peaks = j.get("peaks", {})
    for p in j.get("positions", []):
        d = 1 if p["qty"] > 0 else -1
        pos.add_row(p["symbol"], f"{p['qty']:+g}", f"{p['avg_price']:.2f}", f"{p['market_price']:.2f}",
                    _pct((p["market_price"] / p["avg_price"] - 1) * d),
                    f"{peaks[p['symbol']]:.2f}" if p["symbol"] in peaks else "—")

    orders = Table(title="Ultimi ordini", expand=True)
    for c in ("Ora", "Titolo", "Lato", "Qty", "Motivo", "Stato"):
        orders.add_column(c)
    for ts, sym, side, qty, reason, status in j.db_query(
            "SELECT ts, symbol, side, qty, reason, status FROM orders ORDER BY ts DESC LIMIT 8"):
        orders.add_row(ts[5:16].replace("T", " "), sym, f"[green]{side}[/]" if side == "buy" else f"[red]{side}[/]",
                       f"{qty:g}", reason[:50], status)

    last = j.db_query("SELECT ts, payload FROM events WHERE kind='committee' ORDER BY ts DESC LIMIT 1")
    view = "Nessuna riunione ancora."
    if last:
        d = json.loads(last[0][1]).get("decision") or {}
        targets = "  ".join(f"{t['symbol']} {t['target_weight']:+.0%}" for t in d.get("targets", []))
        view = f"[dim]{last[0][0][11:16]} UTC[/] {d.get('market_view', '-')}\n[bold]Target:[/] {targets}"

    lessons = "\n".join(f"• {l}" for l in j.get("lessons", [])[:5]) or "Nessuna lezione ancora."
    return Group(
        Panel(head, title="Trading Desk"),
        pos,
        orders,
        Panel(view, title="Ultimo comitato"),
        Panel(lessons, title="Lezioni in memoria"),
    )


def run(db_path: str, refresh: float = 5.0) -> None:
    j = Journal(db_path)
    with Live(render(j), refresh_per_second=1, screen=False) as live:
        while True:
            time.sleep(refresh)
            live.update(render(j))
