"use client";
import { useLive } from "@/lib/live";
import { usePulse } from "@/lib/anim";
import { Tape, TopBar } from "@/components/TopBar";
import { EquityPanel, LifeOfDecision, StatePanel, WhereItLands } from "@/components/Panels";
import { Core } from "@/components/Core";
import { AgentLog, BacktestPanel, CorrelationMap, Council, StrategyEngine } from "@/components/Lower";
import { Panel } from "@/components/Panel";

export default function Page() {
  const { state: s, link } = useLive();
  const pulse = usePulse(s?.counters?.trades_today);

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar s={s} link={link} />
      <Tape s={s} />
      {s?.demo && (
        <div className="border-b border-amber/40 bg-amber/10 px-4 py-1.5 text-[11px] text-amber">
          DATI DEMO // prezzi, decisioni e report sono simulati. Il diario reale si riempie con python main.py run.
        </div>
      )}

      <main className="mx-auto grid w-full max-w-[1800px] flex-1 grid-cols-1 gap-3 p-3 xl:grid-cols-12">
        {!s ? (
          <div className="col-span-full grid min-h-[60vh] place-items-center text-mute">
            <span className="cursor">CONNECTING TO PULSE</span>
          </div>
        ) : s.empty ? (
          <div className="col-span-full">
            <Panel title="No data" parts={["Journal empty"]} tag="IDLE" tagColor="#6B7A90">
              <p>Il diario è vuoto. Avvia il bot (<code>python main.py run</code>) oppure prova con dati finti:</p>
              <pre className="mt-2 text-cyan">python main.py simulate{"\n"}DB_PATH=demo.db python main.py app</pre>
            </Panel>
            <div className="mt-3"><BacktestPanel s={s} /></div>
          </div>
        ) : (
          <>
            <div className="xl:col-span-4"><StatePanel s={s} /></div>
            <div className="flex flex-col gap-3 xl:col-span-8">
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <LifeOfDecision s={s} />
                <WhereItLands s={s} />
              </div>
              <EquityPanel s={s} />
            </div>
            <div className="xl:col-span-12"><Core s={s} pulse={pulse} /></div>
            <div className="xl:col-span-3"><CorrelationMap s={s} /></div>
            <div className="xl:col-span-5"><AgentLog s={s} /></div>
            <div className="xl:col-span-4"><StrategyEngine s={s} /></div>
            <div className="xl:col-span-6"><Council s={s} /></div>
            <div className="xl:col-span-6"><BacktestPanel s={s} /></div>
          </>
        )}
      </main>
      <div className="sticky bottom-0 z-30"><Tape s={s} bottom /></div>
    </div>
  );
}
