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
              <p className="mt-4 text-lime">
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
