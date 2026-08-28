import { Disconnected, Field, Label, Section } from "@/components/ui";
import { api, fmt, fmtInt, fmtTime, fmtUsd } from "@/lib/api";
import type { ExperimentResult, Page, Status, TokenInfo } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TokenPage() {
  // The case for the coin is the system's own state, so it is read from the
  // system. Written down, "every result is inconclusive" would be true today
  // and false the first time one is not — on the page where a stale sentence
  // would be least forgivable.
  const [result, statusResult, resultsResult] = await Promise.all([
    api<Page<TokenInfo>>("/api/tokens?limit=50"),
    api<Status>("/api/status"),
    api<Page<ExperimentResult>>("/api/results?limit=200"),
  ]);

  if (!result.ok) return <Disconnected error={result.error} what="token information" />;

  const godgod = result.data.items.find((token) => token.symbol === "GODGOD");
  const observed = result.data.items.filter((token) => token.symbol !== "GODGOD");

  const status = statusResult.ok ? statusResult.data : null;
  const horizons = status?.research.horizons_hours ?? [];
  const longest = horizons.length ? horizons[horizons.length - 1] : null;
  const floor = status?.research.min_group_size ?? null;
  const days = status?.collection.measuring_since
    ? Math.floor((Date.now() - Date.parse(status.collection.measuring_since)) / 86_400_000)
    : null;

  const outcomes = resultsResult.ok ? resultsResult.data.items : [];
  const settled = outcomes.filter((row) => row.outcome !== "INCONCLUSIVE").length;

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
          it needs months. not as a turn of phrase
          {longest !== null ? (
            <>
              {" "}
              — the longest question here reads its outcome {longest} hours after the measurement
              that starts it
            </>
          ) : null}
          {floor !== null ? (
            <>, and nothing counts as a difference until {floor} measurements sit on each side</>
          ) : null}
          .{" "}
          {outcomes.length === 0 ? (
            <>nothing has been answered yet.</>
          ) : settled === 0 ? (
            <>
              all {outcomes.length} results so far say inconclusive
              {days !== null ? `, on ${days} days of history` : null}. that is the honest state,
              and the only fix is more days.
            </>
          ) : (
            <>
              {settled} of {outcomes.length} results have settled
              {days !== null ? `, on ${days} days of history` : null}. the rest need more days,
              not a smaller threshold.
            </>
          )}
        </p>
        <p className="mt-3 text-muted">
          months cost money every day. a machine that doesn&apos;t sleep, a database that keeps
          every measurement, model calls under a hard ceiling. skip a week and the week is gone —
          a detector needs several readings of the same token, and history nobody wrote down
          doesn&apos;t turn up later.
        </p>
        <p className="mt-3 text-muted">
          that is what the coin pays for. the machines, and the people still building this while
          it counts.
        </p>
      </Section>

      <Section title="what it is not">
        <ul className="space-y-1 text-muted">
          <li>— not a share of revenue. there is no revenue.</li>
          <li>— not a prediction. nothing here says where a price goes, this page included.</li>
          <li>
            — not access. every observation, every question, every rejected result is already
            free and stays up.
          </li>
          <li>
            — not a reason to believe the research. that is what the dataset hash and the
            falsification rule are for.
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
