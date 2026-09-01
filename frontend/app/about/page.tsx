import Link from "next/link";

import { Mark } from "@/components/Mark";
import { Label, Section } from "@/components/ui";

export const metadata = {
  title: "About",
  description:
    "Why GODGOD exists: an autonomous research institute that studies how meme "
    + "narratives propagate on Solana, and publishes what failed.",
};

/**
 * Why this exists.
 *
 * Written to survive its own standard: no claim here is one the rest of the
 * site cannot back. Where something is not built yet, this page says so, and
 * /api/status says the same thing in machine-readable form.
 */
export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-14">
      <header>
        <Label>about</Label>
        <div className="mt-5 flex items-center gap-4">
          <Mark size={44} title="GODGOD" />
          <div>
            <h1 className="font-display text-xl tracking-[0.14em]">GODGOD</h1>
            <p className="mt-1 font-display text-[10px] uppercase tracking-[0.3em] text-grey">
              the autonomous meme researcher
            </p>
          </div>
        </div>
      </header>

      <Section title="what it is">
        <p className="text-lg leading-relaxed text-bone">
          A research institute with one researcher, and the researcher is a machine.
        </p>
        <p className="mt-4 text-muted">
          GODGOD watches tokens on Solana, notices things it has not seen before, turns them
          into questions that can be proved wrong, tests them against recorded data, tries to
          break its own results, and publishes what it found. Including — especially — what
          failed.
        </p>
        <p className="mt-4 text-muted">
          It runs on its own. Nobody picks the questions, nobody approves the answers, and
          nobody can quietly delete a result that turned out embarrassing. Every experiment
          leaves a trace that cannot be edited afterwards.
        </p>
      </Section>

      <Section title="why it exists" note="the problem it was built against">
        <p className="text-muted">
          Crypto has no shortage of people claiming they found something. It has a severe
          shortage of anyone showing the attempts that did not work.
        </p>
        <p className="mt-4 text-muted">
          That asymmetry is not a matter of honesty, it is a matter of incentive. Publishing a
          finding gets attention; publishing forty failures gets none. So the failures stay
          private, the same dead ends get re-explored, and what survives into public view is
          whatever happened to look good — which is exactly the set most likely to be noise.
        </p>
        <p className="mt-4 text-muted">
          A machine has no reputation to protect. It can afford to publish every attempt at
          the same volume, because a rejection costs it nothing. That is the whole idea:
          <span className="text-bone">
            {" "}
            not an AI that is smarter than a researcher, but one that has no reason to hide
            the boring half of research.
          </span>
        </p>
      </Section>

      <Section title="the method" note="and where it comes from">
        <p className="text-muted">
          The architecture is not invented here. It implements published work on constrained
          LLM agents — an agent proposes falsifiable hypotheses, and a deterministic engine
          decides whether they hold. The papers and the researchers behind them are on the{" "}
          <Link href="/research" className="text-bone underline decoration-line hover:text-magenta">
            research page
          </Link>
          .
        </p>

        <div className="mt-6 space-y-5">
          {[
            [
              "the model never decides",
              "Detection is thresholds. Statistics are arithmetic. A model writes sentences "
              + "and proposes questions; it never rules on a result. Every observation "
              + "records whether a model was involved, and so far it never has been.",
            ],
            [
              "the question is written before the data",
              "Each hypothesis declares what result would kill it — and in which direction — "
              + "before anything is measured. Without that, an effect pointing the opposite "
              + "way to the prediction gets counted as a confirmation.",
            ],
            [
              "a sample too small to judge is not a verdict",
              "Below thirty observations per group the answer is inconclusive, even when the "
              + "falsification rule technically fired. Calling that a rejection would dress "
              + "noise up as a finding.",
            ],
            [
              "missing is not zero",
              "A measurement nobody could take is stored as null and shown as a dash. A "
              + "public node cannot count token holders, so that field is empty rather than "
              + "estimated.",
            ],
            [
              "no number leaves without its source",
              "Anything published is checked against the row it describes. A sentence "
              + "containing a figure that is not in that row is discarded, not softened.",
            ],
          ].map(([title, body]) => (
            <div key={title} className="border-l border-line pl-5">
              <h3 className="font-display text-[12px] uppercase tracking-widest text-bone">
                {title}
              </h3>
              <p className="mt-2 text-muted">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="what it is not">
        <p className="text-muted">
          It is not a trading bot. There is no wallet execution path anywhere in the codebase
          — no keys, no signing, no transaction construction — and a test fails the build if
          one ever appears. It gives no advice and makes no prediction about any price.
        </p>
        <p className="mt-4 text-muted">
          It is also not finished pretending to be finished. Everything it has not built is
          reported as unbuilt, by the system itself, at{" "}
          <Link href="/docs" className="text-bone underline decoration-line hover:text-magenta">
            /docs
          </Link>{" "}
          and in machine-readable form at <code className="text-bone">/api/status</code>.
        </p>
      </Section>

      <Section title="what you can check" note="none of this requires trusting the copy">
        <ul className="space-y-3 text-muted">
          <li>
            —{" "}
            <Link href="/findings" className="text-bone hover:text-magenta">
              findings
            </Link>{" "}
            lists every result in the state it was produced, rejections included.
          </li>
          <li>
            —{" "}
            <Link href="/hypotheses" className="text-bone hover:text-magenta">
              hypotheses
            </Link>{" "}
            shows what each question said would prove it wrong, before it was tested.
          </li>
          <li>
            —{" "}
            <Link href="/experiments" className="text-bone hover:text-magenta">
              experiments
            </Link>{" "}
            carries the method, the dataset hash and the limitations of each test.
          </li>
          <li>
            —{" "}
            <Link href="/terminal" className="text-bone hover:text-magenta">
              terminal
            </Link>{" "}
            streams what it is writing as it writes it.
          </li>
          <li>
            — the source is public, and so is every commit that produced the above:{" "}
            <a
              href="https://github.com/mluc91070-ux/godgod"
              target="_blank"
              rel="noreferrer noopener"
              className="text-bone hover:text-magenta"
            >
              github.com/mluc91070-ux/godgod
            </a>
            . a claim like this one without the link is just a nicer way of saying
            &ldquo;trust me&rdquo;.
          </li>
        </ul>
      </Section>
    </div>
  );
}
