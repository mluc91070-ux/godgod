import { Disconnected, Field, Label, Section } from "@/components/ui";
import { api, fmt, fmtInt, fmtTime, fmtUsd } from "@/lib/api";
import type { Page, TokenInfo } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TokenPage() {
  const result = await api<Page<TokenInfo>>("/api/tokens?limit=50");

  if (!result.ok) return <Disconnected error={result.error} what="token information" />;

  const godgod = result.data.items.find((token) => token.symbol === "GODGOD");
  const observed = result.data.items.filter((token) => token.symbol !== "GODGOD");

  return (
    <div className="mx-auto max-w-4xl space-y-10">
      <div>
        <Label>token</Label>
        <p className="mt-4 max-w-2xl text-muted">
          Informational only. There is no buy button, no trading, no wallet execution and no price
          claim anywhere in this system. Unknown values are shown as “—” rather than filled in.
        </p>
      </div>

      <Section title="why there is a coin">
        <p className="text-muted">
          This system has to run for months before it can answer anything, and that is not a
          figure of speech. The longest question it asks reads an outcome twelve hours after the
          measurement that triggered it, and no difference is believed until thirty measurements
          sit on each side of it. Every result published so far is inconclusive for exactly that
          reason. The fix is time, not a smaller threshold.
        </p>
        <p className="mt-3 text-muted">
          Running for months costs money every day: a machine that does not sleep, a database
          that keeps every measurement, model calls under a hard daily ceiling. None of it is
          optional. A week not collected is a week that cannot be recovered — a detector needs
          several measurements of the <em>same</em> token, and history nobody wrote down does
          not become available later.
        </p>
        <p className="mt-3 text-muted">
          The coin funds that: the infrastructure it runs on, and the people who keep building
          it while it measures.
        </p>
      </Section>

      <Section title="what it is not">
        <ul className="space-y-2 text-muted">
          <li>
            — <span className="text-bone">not a claim on anything this system earns.</span> It
            earns nothing. There is no revenue, no fee, no trading, no wallet. It has never held
            a token and contains no code path that could sign for one.
          </li>
          <li>
            — <span className="text-bone">not a prediction.</span> No page here says what a
            price will do, including this one. The checks that enforce that are mechanical, not
            a matter of tone.
          </li>
          <li>
            — <span className="text-bone">not access.</span> Every observation, every question
            and every rejected result is on this site for free and stays there. Holding the coin
            unlocks nothing, because nothing is locked.
          </li>
          <li>
            — <span className="text-bone">not a reason to trust the research.</span> The
            research is checkable on its own terms: every experiment publishes its dataset hash,
            its method and the rule that would have killed it.
          </li>
        </ul>
      </Section>

      <Section title="godgod">
        {godgod ? (
          <>
            <Field k="address" v={<span className="break-all">{godgod.address}</span>} />
            <Field k="name" v={godgod.name} />
            <Field k="symbol" v={godgod.symbol} />
            <Field k="decimals" v={godgod.decimals ?? "—"} />
            <Field k="market cap" v={fmtUsd(godgod.market_cap_usd)} />
            <Field k="liquidity" v={fmtUsd(godgod.liquidity_usd)} />
            <Field k="holders" v={fmtInt(godgod.holders)} />
            {godgod.is_demo ? (
              <p className="mt-4 text-amber">
                demo placeholder. this row describes no real asset.
              </p>
            ) : null}
          </>
        ) : (
          <p className="text-muted">no token record.</p>
        )}
      </Section>

      <Section title="observed tokens" note="research subjects, not recommendations">
        <div className="space-y-6">
          {observed.map((token) => (
            <article key={token.id}>
              <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
                <span className="text-bone">{token.symbol ?? "—"}</span>
                <span className="break-all normal-case tracking-normal">{token.address}</span>
                <span>launched {fmtTime(token.launch_time)}</span>
              </div>
              <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted">
                <div className="flex gap-2">
                  <dt>mcap</dt>
                  <dd className="text-bone">{fmtUsd(token.market_cap_usd)}</dd>
                </div>
                <div className="flex gap-2">
                  <dt>liquidity</dt>
                  <dd className="text-bone">{fmtUsd(token.liquidity_usd)}</dd>
                </div>
                <div className="flex gap-2">
                  <dt>holders</dt>
                  <dd className="text-bone">{fmtInt(token.holders)}</dd>
                </div>
                <div className="flex gap-2">
                  <dt>top10 concentration</dt>
                  <dd className="text-bone">{fmt(token.holder_concentration_top10)}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </Section>
    </div>
  );
}
