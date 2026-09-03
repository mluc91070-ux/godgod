import { Label, Section } from "@/components/ui";
import { api, fmtInt } from "@/lib/api";
import { gradeLink, THESES, type LinkGrade } from "@/lib/thesis";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "theses",
  description:
    "Arguments posed before the data existed to settle them, decomposed into the chain of causation they claim, with each link graded against what this system actually measures.",
};

type Coverage = {
  measurements: number;
  fields: Record<string, number>;
  chains: Record<string, number>;
  note: string;
};

const GRADE_COPY: Record<LinkGrade, string> = {
  measured: "measured",
  "partly-measured": "partly measured",
  "not-measured-here": "not measurable here",
  "not-graded": "not graded",
};

const GRADE_COLOUR: Record<LinkGrade, string> = {
  measured: "text-amber",
  "partly-measured": "text-bone",
  "not-measured-here": "text-grey",
  "not-graded": "text-grey",
};

/**
 * A thesis is not a finding, and this page exists to keep it that way.
 *
 * The argument is static and renders unconditionally. That is the correction:
 * the first version fetched the whole page from the API and rendered "no data"
 * whenever the API was asleep or on an older build, which was a lie about an
 * argument that had not changed and told the reader nothing about the deploy.
 * A paragraph does not become truer because a backend answered.
 *
 * The grading is the opposite kind of thing and is treated the opposite way. It
 * is a count over live measurements, it only ever comes from the database, and
 * when the database cannot be reached each link reads "not graded" — which is
 * carefully not "not measurable here". One says nobody asked; the other says we
 * asked and there was nothing. A deploy problem must never be able to dress
 * itself up as a fact about the data.
 */
export default async function ThesisPage() {
  const result = await api<Coverage>("/api/field-coverage");
  const coverage = result.ok ? result.data : null;

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
        database, never taken from the argument.
      </p>

      {coverage === null ? (
        <p className="mt-6 max-w-2xl border border-line p-4 text-[11px] text-muted">
          The measurement API did not answer, so the links below read{" "}
          <span className="text-bone">not graded</span> rather than carrying a number. That is
          not the same as a link with nothing behind it: nobody asked the database this time.
          The argument itself does not depend on it and is unchanged.
        </p>
      ) : null}

      {THESES.map((thesis) => {
        const graded = thesis.chain.map((link) => ({ link, ...gradeLink(link, coverage?.fields ?? null) }));
        const blocked = graded.filter((row) => row.grade === "not-measured-here");
        const chainRows = Object.entries(coverage?.chains ?? {}).sort((a, b) => b[1] - a[1]);

        return (
          <article key={thesis.key} className="mt-12 border-t border-line pt-8">
            <div className="flex flex-wrap items-baseline gap-x-4 text-[10px] uppercase tracking-widest text-muted">
              <span>posed by {thesis.posedBy}</span>
              <span>{thesis.posedAt}</span>
              {coverage === null ? (
                <span className="text-grey">not graded</span>
              ) : blocked.length > 0 ? (
                <span className="text-grey">
                  blocked at {blocked.length} of {graded.length} links
                </span>
              ) : (
                <span className="text-amber">testable end to end</span>
              )}
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
              note={
                coverage
                  ? `graded against ${fmtInt(coverage.measurements)} live measurements`
                  : "the grading needs the measurement API"
              }
            >
              <ul className="divide-y divide-line">
                {graded.map(({ link, grade, counts, unknown }, index) => (
                  <li key={link.step} className="py-3">
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                      <span className="w-5 text-[11px] text-grey">{index + 1}</span>
                      <span className="text-bone">{link.step}</span>
                      <span
                        className={`ml-auto text-[10px] uppercase tracking-widest ${GRADE_COLOUR[grade]}`}
                      >
                        {GRADE_COPY[grade]}
                      </span>
                    </div>
                    <p className="ml-9 mt-1 max-w-2xl text-[11px] text-muted">{link.detail}</p>
                    <div className="ml-9 mt-1 flex flex-wrap gap-x-5 font-mono text-[10px] text-grey">
                      {counts === null
                        ? link.fields.map((name) => <span key={name}>{name}</span>)
                        : Object.entries(counts).map(([name, count]) => (
                            <span key={name} className={count > 0 ? "text-muted" : undefined}>
                              {name} {fmtInt(count)}
                            </span>
                          ))}
                      {unknown.map((name) => (
                        <span key={name}>{name} — not a column</span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
              {blocked.length > 0 ? (
                <p className="mt-4 max-w-2xl text-[11px] text-muted">
                  {blocked.map((row) => row.link.step).join(" and ")} cannot be measured by this
                  deployment. A public node cannot count holders — that needs an indexer — so
                  the field is NULL on every live row rather than estimated, and the links that
                  depend on it have nothing to read. The thesis is published with the gap rather
                  than without it.
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
        );
      })}
    </main>
  );
}
