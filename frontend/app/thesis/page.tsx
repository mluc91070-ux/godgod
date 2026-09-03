import { Disconnected, Empty, Label, Section } from "@/components/ui";
import { api, fmtInt } from "@/lib/api";
import type { Theses, ThesisLink } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "theses",
  description:
    "Arguments posed before the data existed to settle them, decomposed into the chain of causation they claim, with each link graded against what this system actually measures.",
};

const STATUS_COPY: Record<ThesisLink["status"], string> = {
  measured: "measured",
  "partly-measured": "partly measured",
  "not-measured-here": "not measurable here",
};

const STATUS_COLOUR: Record<ThesisLink["status"], string> = {
  measured: "text-amber",
  "partly-measured": "text-bone",
  "not-measured-here": "text-grey",
};

/**
 * A thesis is not a finding, and this page exists to keep it that way.
 *
 * Someone wrote an argument about why one chain might behave differently from
 * another. That is worth publishing — committing to a mechanism before the
 * result is known is the only part of it that can ever be checked — and it is
 * worth publishing in a form that cannot be mistaken for a result.
 *
 * So a thesis is stored as a chain rather than a paragraph, because a
 * mechanism is only as testable as its weakest link, and each link is graded
 * by counting the live measurements that carry the fields it needs. The file
 * may claim a mechanism. It may not claim the mechanism was measured. When two
 * of five links come back with zero rows, the page says so with the number.
 */
export default async function ThesisPage() {
  const result = await api<Theses>("/api/theses");

  if (!result.ok) {
    return <Disconnected error={result.error} what="the posed theses" />;
  }

  const { theses, measurements, chains, note } = result.data;
  const chainRows = Object.entries(chains).sort((a, b) => b[1] - a[1]);

  return (
    <main className="mx-auto max-w-4xl px-5 py-16">
      <Label>theses</Label>
      <h1 className="mt-2 text-2xl text-bone">arguments, posed before the answer</h1>

      <p className="mt-5 max-w-2xl text-muted">
        A thesis is an argument about a mechanism, written before the measurements exist to
        settle it. It has no dataset, no horizon and no verdict, and nothing on this page was
        produced by an experiment.
      </p>
      <p className="mt-3 max-w-2xl text-muted">
        It is here because committing to an explanation <em>before</em> the result is known is
        the part that can be checked later. Written as a chain rather than a paragraph, it also
        shows exactly where it stops being testable — and that grade is counted from the
        database, not taken from the file.
      </p>

      {theses.length === 0 ? (
        <div className="mt-10">
          <Empty>{note}</Empty>
        </div>
      ) : (
        theses.map((thesis) => (
          <article key={thesis.key} className="mt-12 border-t border-line pt-8">
            <div className="flex flex-wrap items-baseline gap-x-4 text-[10px] uppercase tracking-widest text-muted">
              <span>posed by {thesis.posed_by}</span>
              {thesis.posed_at ? <span>{thesis.posed_at}</span> : null}
              <span className={thesis.testable_end_to_end ? "text-amber" : "text-grey"}>
                {thesis.testable_end_to_end
                  ? "testable end to end"
                  : `blocked at ${thesis.blocked_at.length} of ${thesis.chain_of_causation.length} links`}
              </span>
            </div>

            <h2 className="mt-3 text-xl text-bone">{thesis.title}</h2>
            <p className="mt-4 max-w-2xl">{thesis.claim}</p>

            <Section title="the argument" note="as posed, untested">
              <div className="space-y-3">
                {thesis.argument.map((line, index) => (
                  <p key={index} className="max-w-2xl text-muted">
                    {line}
                  </p>
                ))}
              </div>
            </Section>

            <Section
              title="the chain of causation"
              note={`graded against ${fmtInt(measurements)} live measurements`}
            >
              <ul className="divide-y divide-line">
                {thesis.chain_of_causation.map((link, index) => (
                  <li key={link.step} className="py-3">
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                      <span className="w-5 text-[11px] text-grey">{index + 1}</span>
                      <span className="text-bone">{link.step}</span>
                      <span
                        className={`ml-auto text-[10px] uppercase tracking-widest ${STATUS_COLOUR[link.status]}`}
                      >
                        {STATUS_COPY[link.status]}
                      </span>
                    </div>
                    <p className="ml-9 mt-1 max-w-2xl text-[11px] text-muted">{link.detail}</p>
                    <div className="ml-9 mt-1 flex flex-wrap gap-x-5 font-mono text-[10px] text-grey">
                      {Object.entries(link.measured_fields).map(([name, count]) => (
                        <span key={name} className={count > 0 ? "text-muted" : undefined}>
                          {name} {fmtInt(count)}
                        </span>
                      ))}
                      {link.unknown_fields.map((name) => (
                        <span key={name}>{name} — not a column</span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
              {thesis.blocked_at.length > 0 ? (
                <p className="mt-4 max-w-2xl text-[11px] text-muted">
                  {thesis.blocked_at.join(" and ")} cannot be measured by this deployment. A
                  public node cannot count holders — that needs an indexer — so the field is
                  NULL on every live row rather than estimated, and the links that depend on it
                  have nothing to read. The thesis is published with the gap rather than
                  without it.
                </p>
              ) : null}
            </Section>

            <Section title="what would kill it" note="written with the thesis, not after">
              <p className="max-w-2xl text-muted">{thesis.falsification}</p>
            </Section>

            <Section
              title="what would fake it"
              note={`${thesis.confounds.length} confounds named in advance`}
            >
              <ul className="divide-y divide-line">
                {thesis.confounds.map((confound) => (
                  <li key={confound.name} className="py-3">
                    <div className="text-bone">{confound.name}</div>
                    <p className="mt-1 max-w-2xl text-[11px] text-muted">{confound.detail}</p>
                  </li>
                ))}
              </ul>
              {chainRows.length > 0 ? (
                <p className="mt-4 text-[11px] text-muted">
                  measured so far:{" "}
                  {chainRows.map(([chain, count]) => `${fmtInt(count)} on ${chain}`).join(", ")}.
                  {chainRows.length < 2
                    ? " a contrast between two chains needs both of them, and one side is empty."
                    : null}
                </p>
              ) : null}
            </Section>
          </article>
        ))
      )}
    </main>
  );
}
