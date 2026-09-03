import Link from "next/link";

import ResearchAge from "@/components/ResearchAge";
import { HypothesisExample } from "@/components/examples";
import { Empty, Label, Nothing, Tag } from "@/components/ui";
import { api, fmt, fmtInt } from "@/lib/api";
import type { Experiment, ExperimentResult, Hypothesis, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

const STATUSES = ["PROPOSED", "TESTING", "SUPPORTED", "REJECTED", "INCONCLUSIVE"];

type Props = { searchParams: Promise<{ status?: string }> };

type Run = { experiment: Experiment; result?: ExperimentResult };

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 text-muted sm:grid sm:grid-cols-[5rem_1fr] sm:gap-4">
      <span>{k}</span>
      <span>{children}</span>
    </div>
  );
}

/**
 * What happened when the question was actually run.
 *
 * A status and a confidence score is not a result. Four questions all reading
 * INCONCLUSIVE at confidence 0.15 tell a reader nothing about whether the data
 * disagreed with the hypothesis, agreed too weakly to say, or — as happened
 * twice here — never produced a single exposed row, so there was nothing to
 * compare at all. Three different outcomes wearing one label, and the numbers
 * that separate them were already in the API.
 *
 * The empty arm is drawn in magenta because it is the one case that is not
 * about the market: it means the trigger never fired, which is a fact about
 * the detector rather than about any token, and it is fixed by changing the
 * exposure rather than by waiting for more data.
 *
 * Nothing is computed here. Every figure is read from the stored result, and
 * anything the result did not record is left out rather than filled in.
 */
function Verdict({ run }: { run?: Run }) {
  if (!run) {
    return (
      <p className="mt-2 text-[11px] text-muted">
        posed, not yet run — no experiment has been built against it.
      </p>
    );
  }

  const { experiment, result } = run;
  if (!result) {
    return (
      <p className="mt-2 text-[11px] text-muted">
        experiment #{experiment.seq ?? "—"} built on {fmtInt(experiment.sample_size)} rows, no
        result recorded yet.
      </p>
    );
  }

  const m = (result.metrics ?? {}) as Record<string, number>;
  const exposed = m.n_exposed;
  const control = m.n_control;
  const gap = m.difference_pp;
  const needed = (experiment.parameters ?? {})["min_effect_pp"] as number | undefined;
  const excluded = (m.excluded_rows ?? {}) as unknown as Record<string, number>;
  const dropped = Object.entries(excluded).sort((a, b) => b[1] - a[1]);
  const emptyArm = exposed === 0 || control === 0;
  const failedChecks = Object.entries(result.critic_checks ?? {})
    .filter(([key, value]) => key !== "version" && value !== "PASS")
    .map(([key]) => key);

  return (
    <div className="mt-2 space-y-1 text-[11px]">
      <Row k="measured">
        {exposed === undefined || control === undefined ? (
          <span className="text-muted">the groups were not recorded</span>
        ) : (
          <span className={emptyArm ? "text-magenta" : "text-bone"}>
            {fmtInt(exposed)} exposed vs {fmtInt(control)} control
            {emptyArm ? " — one side is empty, so nothing was compared" : null}
            {!emptyArm && m.rate_exposed !== undefined && m.rate_control !== undefined
              ? ` · ${Math.round(m.rate_exposed * 100)}% vs ${Math.round(m.rate_control * 100)}%`
              : null}
          </span>
        )}
      </Row>

      {gap !== undefined ? (
        <Row k="gap">
          <span className="text-bone">
            {gap > 0 ? "+" : ""}
            {fmt(gap, 1)} points
            {needed !== undefined ? (
              <span className="text-muted"> · {needed} needed to count</span>
            ) : null}
            {m.expected_direction !== undefined && gap * m.expected_direction < 0 ? (
              <span className="text-magenta"> · against the predicted direction</span>
            ) : null}
          </span>
        </Row>
      ) : null}

      {m.distinct_tokens !== undefined ? (
        <Row k="tokens">
          <span className="text-bone">{fmtInt(m.distinct_tokens)}</span>
          <span className="text-muted">
            {" "}
            — consecutive readings of one token are correlated, so this is closer to the real
            sample size than the row count is
          </span>
        </Row>
      ) : null}

      <Row k="why">{result.summary}</Row>

      {result.critic_verdict ? (
        <Row k="critic">
          <span className={result.critic_verdict === "FAIL" ? "text-magenta" : "text-bone"}>
            {result.critic_verdict}
          </span>
          {failedChecks.length ? (
            <span className="text-muted"> · {failedChecks.join(", ")}</span>
          ) : null}
        </Row>
      ) : null}

      {dropped.length ? (
        <Row k="rows dropped">
          <span className="text-grey">
            {dropped.map(([reason, count]) => `${reason} ${fmtInt(count)}`).join(" · ")}
          </span>
        </Row>
      ) : null}
    </div>
  );
}

export default async function HypothesesPage({ searchParams }: Props) {
  const { status } = await searchParams;
  const filter = status?.toUpperCase();

  // The question, and what actually happened when it was run. They lived on
  // separate pages, and this one showed a status and a confidence score — a
  // reader could see four questions all reading INCONCLUSIVE and nothing about
  // why. Inconclusive is not a result until it says which side was empty.
  const [result, experiments, results] = await Promise.all([
    api<Page<Hypothesis>>(
      `/api/hypotheses?limit=100${filter ? `&status=${encodeURIComponent(filter)}` : ""}`,
    ),
    api<Page<Experiment>>("/api/experiments?limit=100"),
    api<Page<ExperimentResult>>("/api/results?limit=100"),
  ]);

  // hypothesis -> its result, joined through the experiment. Both lookups may
  // miss: a question posed but never run has no experiment, which is a real
  // state and reads as "posed, not yet run" rather than as a blank.
  const resultByExperiment = new Map(
    (results.ok ? results.data.items : []).map((row) => [row.experiment_id, row]),
  );
  const runFor = new Map<string, Run>();
  for (const experiment of experiments.ok ? experiments.data.items : []) {
    runFor.set(experiment.hypothesis_id, {
      experiment,
      result: resultByExperiment.get(experiment.id),
    });
  }

  if (!result.ok) {
    return (
      <div className="mx-auto max-w-4xl">
        <Label>hypotheses</Label>
        <div className="mt-6">
          <Nothing
            what="hypotheses"
            unreachable
            error={result.error}
            because=""
            needs={[
              "each question this system has posed, with its population, its horizon and its baseline",
              "the rule that would falsify it is fixed when the question is written, never after the result",
              "questions come from templates, so nothing reads the data before choosing what to claim about it",
            ]}
          >
            <HypothesisExample />
          </Nothing>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>hypotheses</Label>
        <span className="text-[10px] text-muted">{result.data.total} recorded</span>
      </div>

      <p className="mt-4 max-w-2xl text-muted">
        each question states what would prove it wrong before it is tested. open one to see the
        design, the memories consulted while writing it, and the experiments run against it.
      </p>

      <div className="mt-6 flex flex-wrap gap-3 text-[10px] uppercase tracking-widest">
        <Link
          href="/hypotheses"
          className={`border px-2 py-[2px] ${filter ? "border-line text-muted" : "border-bone text-bone"}`}
        >
          all
        </Link>
        {STATUSES.map((name) => (
          <Link
            key={name}
            href={`/hypotheses?status=${name.toLowerCase()}`}
            className={`border px-2 py-[2px] ${
              filter === name ? "border-bone text-bone" : "border-line text-muted"
            }`}
          >
            {name.toLowerCase()}
          </Link>
        ))}
      </div>

      <div className="mt-8">
        {result.data.items.length === 0 ? (
          filter ? (
            <Empty>no hypothesis has been recorded under that filter.</Empty>
          ) : (
            <ResearchAge what="question has been posed">
              <HypothesisExample />
            </ResearchAge>
          )
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {result.data.items.map((hypothesis) => (
              <li key={hypothesis.id}>
                <Link
                  href={`/hypotheses/${hypothesis.id}`}
                  className="block py-4 hover:bg-surface"
                >
                  <div className="flex flex-col gap-1 sm:grid sm:grid-cols-[5rem_1fr_8rem] sm:items-baseline sm:gap-4">
                    <span className="text-muted">
                      #{String(hypothesis.seq ?? 0).padStart(6, "0")}
                    </span>
                    <span>{hypothesis.question}</span>
                    <span className="flex justify-start sm:justify-end">
                      <Tag value={hypothesis.status} />
                    </span>
                  </div>
                  <Verdict run={runFor.get(hypothesis.id)} />
                  <p className="mt-2 flex flex-col gap-0.5 text-[11px] text-muted sm:grid sm:grid-cols-[5rem_1fr] sm:gap-4">
                    <span>falsified if</span>
                    <span className="text-amber">{hypothesis.falsification_condition}</span>
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
