"""Notifiche e comandi Telegram (come in freqtrade). Accetta comandi solo dalla chat configurata.

Comandi:
  /status            equity, P/L di oggi, posizioni
  /lezioni           le lezioni che il bot ha imparato dai trade chiusi
  /kill CONFERMA     chiude tutte le posizioni e ferma il bot (al prossimo tick)
  /resume            riattiva il bot
"""
from __future__ import annotations

import json
import logging
import threading
import urllib.parse
import urllib.request

from .journal import Journal

log = logging.getLogger("desk.telegram")


class Telegram:
    def __init__(self, token: str, chat_id: str, journal: Journal):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)
        self.j = journal
        self._offset = 0

    def _call(self, method: str, params: dict, timeout: int = 10) -> dict:
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(f"{self.base}/{method}", data=data, timeout=timeout) as r:
            return json.loads(r.read())

    def send(self, text: str) -> None:
        try:
            self._call("sendMessage", {"chat_id": self.chat_id, "text": text[:4000]})
        except Exception as e:  # una notifica persa non deve mai fermare il trading
            log.warning("Telegram non raggiungibile: %s", e)

    # ---------- Comandi ----------

    def handle(self, text: str) -> str:
        cmd, _, arg = text.strip().partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd == "/status":
            row = self.j.db_query("SELECT equity, mode FROM equity WHERE mode != 'SHADOW' ORDER BY ts DESC LIMIT 1")
            pos = self.j.get("positions", [])
            lines = [f"Modalità {row[0][1]} | equity {row[0][0]:,.0f} $" if row else "Nessun dato ancora."]
            lines += [f"{p['symbol']}: {p['qty']:+g} @ {p['avg_price']:.2f} (ora {p['market_price']:.2f})" for p in pos]
            lines.append(f"Fermo: {'sì' if self.j.get('halted') else 'no'}")
            return "\n".join(lines)
        if cmd == "/lezioni":
            lessons = self.j.get("lessons", [])
            return "\n".join(f"• {l}" for l in lessons) or "Nessuna lezione ancora."
        if cmd == "/kill":
            if arg.strip().upper() != "CONFERMA":
                return "Per chiudere tutto e fermare il bot scrivi: /kill CONFERMA"
            self.j.set("kill_requested", True)
            return "Ricevuto: chiudo tutte le posizioni al prossimo tick e fermo il bot."
        if cmd == "/resume":
            self.j.set("halted", False)
            return "Bot riattivato."
        return __doc__.split("Comandi:")[1]

    def poll_once(self, timeout: int = 25) -> None:
        res = self._call("getUpdates", {"offset": self._offset, "timeout": timeout}, timeout=timeout + 5)
        for upd in res.get("result", []):
            self._offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != self.chat_id or "text" not in msg:
                continue  # ignora chiunque non sia la chat autorizzata
            self.send(self.handle(msg["text"]))

    def start_polling(self) -> threading.Thread:
        def loop():
            while True:
                try:
                    self.poll_once()
                except Exception as e:
                    log.warning("Polling Telegram: %s", e)
                    threading.Event().wait(10)

        t = threading.Thread(target=loop, daemon=True, name="telegram")
        t.start()
        return t
