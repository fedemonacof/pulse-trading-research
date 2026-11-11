"""Il comitato di investimento.

Pipeline (la stessa a cui sono arrivati TradingAgents e ai-hedge-fund):
  1. Analisti in parallelo: tecnico/quant, notizie, macro (web), fondamentali (web)
  2. Dibattito: ricercatore rialzista vs ribassista, N round
  3. Panel di rischio: aggressivo / neutrale / conservativo
  4. Gestore di portafoglio, con la memoria delle lezioni dei trade passati
  + Riflessione: dopo i trade chiusi, un agente scrive le lezioni da ricordare

Gli agenti PROPONGONO pesi target. Non toccano mai il broker: i limiti di rischio
e l'esecuzione sono codice deterministico in risk.py ed engine.py.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel

from .config import RiskLimits, Settings

log = logging.getLogger("desk.agents")

FALLBACK_BETA = "server-side-fallback-2026-07-01"


# ---------- Output strutturati ----------

class SymbolView(BaseModel):
    symbol: str
    stance: float        # -1 = fortemente ribassista, +1 = fortemente rialzista
    confidence: float    # 0..1
    rationale: str


class AnalystReport(BaseModel):
    summary: str
    views: list[SymbolView]


class RiskReview(BaseModel):
    aggressive: str
    neutral: str
    conservative: str
    recommended_gross_exposure: float   # frazione dell'equity suggerita dal panel
    event_risks: list[str]


class TargetPosition(BaseModel):
    symbol: str
    target_weight: float  # frazione dell'equity, negativa = short. 0 = nessuna posizione
    confidence: float     # 0..1
    thesis: str
    invalidation: str     # cosa deve succedere per ammettere di avere torto


class PortfolioDecision(BaseModel):
    market_view: str
    targets: list[TargetPosition]


class Lessons(BaseModel):
    lessons: list[str]    # regole brevi e operative, la più importante per prima


@dataclass
class CommitteeResult:
    reports: dict[str, str] = field(default_factory=dict)
    decision: PortfolioDecision | None = None


# ---------- Prompt ----------

COMMON = (
    "Lavori in un desk di trading sistematico che gestisce un conto reale o paper. "
    "Scrivi in italiano. Sii onesto sull'incertezza: 'nessuna posizione' è spesso la scelta migliore, "
    "e ogni operazione costa spread e slippage. Non inventare dati: usa solo quelli forniti o trovati."
)

TECHNICAL = COMMON + (
    "\n\nRuolo: analista quantitativo/tecnico. Ricevi indicatori calcolati (trend, momentum, RSI, MACD, "
    "ATR, volatilità, VWAP intraday) e un quant_score da -1 a 1 prodotto da una regola trend+momentum "
    "testata in backtest. Valuta trend multi-orizzonte, ipercomprato/ipervenduto, regime di volatilità e "
    "qualità del segnale. Per ogni titolo dai stance da -1 a 1 e confidence da 0 a 1."
)

NEWS = COMMON + (
    "\n\nRuolo: analista di notizie ed eventi. Ricevi i titoli e i riassunti recenti. Distingui notizie che "
    "cambiano i fondamentali (utili, guidance, M&A, regolatori, cause) dal rumore. Valuta se la notizia è già "
    "nel prezzo. Senza notizie rilevanti, stance 0 e confidence bassa."
)

MACRO = COMMON + (
    "\n\nRuolo: strategist macro senior. Usa la ricerca web per verificare OGGI: calendario macro "
    "(Fed/BCE, CPI, occupazione), rendimenti dei Treasury, dollaro, petrolio, VIX e sentiment generale. "
    "Concludi con il regime di mercato (risk-on / risk-off / neutro), i rischi evento delle prossime 48 ore "
    "e cosa implica per la watchlist. Massimo 350 parole, cita le fonti."
)

FUNDAMENTAL = COMMON + (
    "\n\nRuolo: analista fondamentale con esperienza da investment banker. Usa la ricerca web per ogni "
    "titolo della watchlist (per gli ETF guarda i principali componenti): data della prossima trimestrale, "
    "ultima guidance, crescita ricavi e margini, valutazione (P/E forward, EV/EBITDA) rispetto alla storia "
    "e ai concorrenti, revisioni delle stime degli analisti, eventi societari. Valuta con tre lenti: "
    "valore (margine di sicurezza), crescita (qualità e durata della crescita), contrarian (cosa sta "
    "prezzando male il mercato). Per ogni titolo una riga di giudizio. Massimo 450 parole, cita le fonti."
)

BULL = COMMON + (
    "\n\nRuolo: ricercatore RIALZISTA. Costruisci il caso più forte possibile per le posizioni long "
    "(o per chiudere gli short) sui titoli della watchlist, usando le prove dei report. Se c'è un "
    "argomento ribassista precedente, rispondi punto per punto. Ammetti dove il caso è debole. Max 300 parole."
)

BEAR = COMMON + (
    "\n\nRuolo: ricercatore RIBASSISTA. Costruisci il caso più forte possibile contro le posizioni long "
    "(o a favore degli short) sui titoli della watchlist, usando le prove dei report. Se c'è un "
    "argomento rialzista precedente, rispondi punto per punto. Ammetti dove il caso è debole. Max 300 parole."
)

RISK_PANEL = COMMON + (
    "\n\nRuolo: panel di rischio con tre voci. AGGRESSIVO: dove il desk sta lasciando rendimento sul tavolo. "
    "NEUTRALE: equilibrio tra rendimento atteso e rischio. CONSERVATIVO: cosa può andare storto, "
    "concentrazione, correlazione tra le posizioni, eventi binari, liquidità. Ognuno in massimo 120 parole. "
    "Poi indica l'esposizione lorda raccomandata (0..1) e l'elenco dei rischi evento."
)

MANAGER = COMMON + (
    "\n\nRuolo: gestore di portafoglio. Ricevi i report degli analisti, il dibattito, il panel di rischio, "
    "il portafoglio attuale, i limiti e le lezioni apprese dai trade passati. Decidi il peso target di ogni "
    "titolo della watchlist (frazione dell'equity; negativo = short). Regole:\n"
    "- Rispetta i limiti forniti; il codice comunque taglierà ciò che li supera.\n"
    "- Opera solo se gli analisti convergono o se un segnale è forte e motivato; nel dubbio peso 0 o mantieni.\n"
    "- Dimensiona in base a convinzione e volatilità: più volatile = posizione più piccola.\n"
    "- Evita di girare il portafoglio per piccole variazioni: cambia il peso solo se la tesi è cambiata.\n"
    "- Prima di eventi binari (trimestrali, Fed) riduci l'esposizione sui titoli coinvolti.\n"
    "- Applica le lezioni apprese, se pertinenti.\n"
    "- Per ogni posizione scrivi tesi e condizione di invalidazione."
)

REFLECTION = COMMON + (
    "\n\nRuolo: responsabile della revisione post-trade. Ricevi i trade chiusi con tesi iniziale, motivo di "
    "uscita e risultato, più le lezioni già esistenti. Separa la sfortuna dagli errori di processo. "
    "Restituisci al massimo 12 lezioni operative, brevi e verificabili (es. 'non aprire long su titoli con "
    "trimestrale entro 2 giorni'), unendo o eliminando quelle vecchie smentite dai dati."
)


# ---------- Comitato ----------

class Committee:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        self.s = settings
        self.client = client or anthropic.Anthropic()

    # Ogni chiamata usa il fallback lato server: se un modello rifiuta, l'API riprova su un altro.
    def _parse(self, system: str, user: str, schema: type[BaseModel], effort: str):
        resp = self.client.beta.messages.parse(
            model=self.s.model,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            log.warning("Risposta strutturata non utilizzabile (stop_reason=%s)", resp.stop_reason)
            return None
        return resp.parsed_output

    def _text(self, system: str, user: str, web: bool = False, max_uses: int = 8) -> str:
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}] if web else []
        messages = [{"role": "user", "content": user}]
        resp = None
        # Con i server tool la risposta può fermarsi con pause_turn: si continua rimandando il contenuto.
        for _ in range(4):
            with self.client.beta.messages.stream(
                model=self.s.model,
                max_tokens=32000,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": self.s.analyst_effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                tools=tools,
                messages=messages,
            ) as stream:
                resp = stream.get_final_message()
            if resp.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
        if resp is None or resp.stop_reason == "refusal":
            return "Report non disponibile."
        return "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    @staticmethod
    def _fmt_report(r: AnalystReport | None) -> str:
        if r is None:
            return "Report non disponibile."
        lines = [r.summary] + [
            f"- {v.symbol}: stance {v.stance:+.2f}, confidence {v.confidence:.2f}. {v.rationale}" for v in r.views
        ]
        return "\n".join(lines)

    @staticmethod
    def _fmt_risk(r: RiskReview | None) -> str:
        if r is None:
            return "Panel di rischio non disponibile."
        return (
            f"AGGRESSIVO: {r.aggressive}\nNEUTRALE: {r.neutral}\nCONSERVATIVO: {r.conservative}\n"
            f"Esposizione lorda raccomandata: {r.recommended_gross_exposure:.0%}\n"
            f"Rischi evento: {'; '.join(r.event_risks) or 'nessuno'}"
        )

    def _debate(self, dossier: str) -> str:
        bull = bear = ""
        transcript = []
        for i in range(max(1, self.s.debate_rounds)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                fb = pool.submit(self._text, BULL, dossier + (f"\n\nARGOMENTO RIBASSISTA PRECEDENTE:\n{bear}" if bear else ""))
                fr = pool.submit(self._text, BEAR, dossier + (f"\n\nARGOMENTO RIALZISTA PRECEDENTE:\n{bull}" if bull else ""))
                bull, bear = fb.result(), fr.result()
            transcript.append(f"--- Round {i + 1} ---\nRIALZISTA:\n{bull}\n\nRIBASSISTA:\n{bear}")
        return "\n\n".join(transcript)

    def run(self, snapshots: dict, news: list, portfolio: dict, limits: RiskLimits,
            lessons: list[str] | None = None, context: dict | None = None) -> CommitteeResult:
        """context: dati gratuiti da freedata.FreeData.briefing (macro FRED, calendario, fondamentali)."""
        symbols = list(snapshots)
        watch = ", ".join(symbols)
        news_txt = "\n".join(
            f"[{n.created_at:%Y-%m-%d %H:%M}] ({','.join(n.symbols)}) {n.headline} — {n.summary}" for n in news[:40]
        ) or "Nessuna notizia recente."
        web = self.s.web_research
        ctx = context or {}
        macro_data = json.dumps({"tassi_e_vix_FRED": ctx.get("macro"), "calendario_macro": ctx.get("calendario")},
                                ensure_ascii=False, default=str)
        fund_data = json.dumps(ctx.get("fondamentali"), ensure_ascii=False, default=str)
        have_macro, have_fund = bool(ctx.get("macro")), bool(ctx.get("fondamentali"))
        # Con i dati ufficiali già in mano bastano poche ricerche web: meno costi, meno numeri inventati
        official = ("\n\nDATI UFFICIALI GIÀ RACCOLTI (usali come base, non cercarli di nuovo; usa la ricerca "
                    "web solo per ciò che manca):\n")

        # 1. Analisti in parallelo
        with ThreadPoolExecutor(max_workers=4) as pool:
            f_tech = pool.submit(self._parse, TECHNICAL, "Indicatori:\n" + json.dumps(snapshots, indent=1),
                                 AnalystReport, self.s.analyst_effort)
            f_news = pool.submit(self._parse, NEWS, f"Watchlist: {watch}\n\nNotizie:\n{news_txt}",
                                 AnalystReport, self.s.analyst_effort)
            f_macro = pool.submit(
                self._text, MACRO, f"Watchlist: {watch}. Prepara il briefing macro di oggi."
                + (official + macro_data if have_macro else ""), web, 3 if have_macro else 8)
            f_fund = pool.submit(
                self._text, FUNDAMENTAL, f"Watchlist: {watch}. Prepara l'analisi fondamentale."
                + (official + fund_data if have_fund else ""), web, 4 if have_fund else 8)
            reports = {
                "tecnico": self._fmt_report(f_tech.result()),
                "notizie": self._fmt_report(f_news.result()),
                "macro": f_macro.result(),
                "fondamentale": f_fund.result(),
            }
        dossier = (
            f"WATCHLIST: {watch}\nPORTAFOGLIO: {json.dumps(portfolio)}\n\n"
            + "\n\n".join(f"=== REPORT {k.upper()} ===\n{v}" for k, v in reports.items())
        )

        # 2. Dibattito rialzista vs ribassista
        reports["dibattito"] = self._debate(dossier)

        # 3. Panel di rischio: riceve anche il calendario e le date delle trimestrali (eventi binari)
        events = json.dumps({
            "calendario_macro": ctx.get("calendario"),
            "trimestrali": {s: f.get("prossima_trimestrale") for s, f in (ctx.get("fondamentali") or {}).items()},
        }, ensure_ascii=False, default=str)
        risk = self._parse(RISK_PANEL, f"LIMITI: {json.dumps(limits.__dict__)}\n\nEVENTI IN ARRIVO: {events}\n\n"
                           f"{dossier}\n\n=== DIBATTITO ===\n{reports['dibattito']}", RiskReview, self.s.analyst_effort)
        reports["rischio"] = self._fmt_risk(risk)

        # 4. Gestore di portafoglio
        memory = "\n".join(f"- {l}" for l in (lessons or [])) or "Nessuna lezione ancora."
        brief = (
            f"LIMITI: {json.dumps(limits.__dict__)}\n\nINDICATORI: {json.dumps(snapshots)}\n\n"
            f"EVENTI IN ARRIVO: {events}\n\n"
            f"LEZIONI APPRESE:\n{memory}\n\n{dossier}\n\n"
            f"=== DIBATTITO ===\n{reports['dibattito']}\n\n=== PANEL DI RISCHIO ===\n{reports['rischio']}"
        )
        decision = self._parse(MANAGER, brief, PortfolioDecision, self.s.manager_effort)
        return CommitteeResult(reports=reports, decision=decision)

    def reflect(self, closed_trades: list[dict], lessons: list[str]) -> list[str]:
        user = (
            f"LEZIONI ESISTENTI:\n{json.dumps(lessons, ensure_ascii=False)}\n\n"
            f"TRADE CHIUSI:\n{json.dumps(closed_trades, ensure_ascii=False, default=str, indent=1)}"
        )
        out = self._parse(REFLECTION, user, Lessons, self.s.manager_effort)
        return out.lessons[:12] if out else lessons
