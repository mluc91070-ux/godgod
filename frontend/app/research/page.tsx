import { Label, Section } from "@/components/ui";

export const metadata = {
  title: "Research",
  description:
    "The published work GODGOD is built on: constrained LLM agents doing falsifiable "
    + "empirical discovery under a deterministic engine.",
};

/**
 * The research this system is built on.
 *
 * Every link was checked before it was written down, and the page says which
 * ones could be opened directly. SSRN and ResearchGate answer automated
 * requests with 403, so those three are confirmed by an index listing the
 * matching title and authors rather than by fetching the page — a weaker check,
 * and stated as one.
 *
 * Where a profile could not be distinguished from a namesake, the person is
 * listed without a link. On a site whose whole claim is that it does not
 * fabricate sources, a plausible-looking wrong URL is the most damaging thing
 * it could publish.
 */

type Link = { label: string; href: string };

const PAPERS: {
  title: string;
  authors: string;
  year: string;
  venue: string;
  abstract: string;
  why: string;
  links: Link[];
}[] = [
  {
    title: "From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency Markets",
    authors: "Yikuan Huang, Zheqi Fan, Kaiqi Hu, Yifan Ye",
    year: "29 April 2026",
    venue: "arXiv:2604.26747 — q-fin.PM, q-fin.GN, q-fin.TR",
    abstract:
      "LLM agents are promising tools for empirical discovery, but their flexibility "
      + "can also turn discovery into uncontrolled search. Our framework casts the task "
      + "as sequential hypothesis search: an agent reads an append-only experiment "
      + "trace, proposes falsifiable factor hypotheses, and maps them to executable "
      + "recipes, while a deterministic engine enforces fixed data splits, selection "
      + "gates, transaction costs, and portfolio tests. Candidate actions are "
      + "restricted to a point-in-time factor DSL, making both successful and failed "
      + "hypotheses auditable.",
    why:
      "This is the architecture. An agent proposes falsifiable hypotheses; a "
      + "deterministic engine decides. The append-only trace and the auditability of "
      + "failed hypotheses are the parts this system took most directly — every "
      + "experiment here writes an immutable trace, and the rejections are published "
      + "beside the rest.",
    links: [
      { label: "arXiv abstract", href: "https://arxiv.org/abs/2604.26747" },
      { label: "PDF", href: "https://arxiv.org/pdf/2604.26747" },
      { label: "Full text (HTML)", href: "https://arxiv.org/html/2604.26747v1" },
      {
        label: "SSRN",
        href: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6715480",
      },
      { label: "RePEc / IDEAS", href: "https://ideas.repec.org/p/arx/papers/2604.26747.html" },
    ],
  },
  {
    title:
      "Beyond Prompting: An Autonomous Framework for Systematic Factor Investing via Agentic AI",
    authors: "Allen Yikuan Huang, Zheqi Fan",
    year: "2026",
    venue: "arXiv:2603.14288",
    abstract:
      "Rather than relying on sequential manual prompts, the model is operationalised "
      + "as a self-directed engine that endogenously formulates interpretable trading "
      + "signals. To mitigate data snooping, the closed-loop system imposes empirical "
      + "discipline through out-of-sample validation and economic rationale "
      + "requirements.",
    why:
      "The same direction, pushed further: moving the model from text generator to a "
      + "participant in systematic discovery. The out-of-sample discipline and the "
      + "requirement that a signal have an economic rationale are why this system "
      + "writes a falsification condition before it looks at the data.",
    links: [
      { label: "arXiv abstract", href: "https://arxiv.org/abs/2603.14288" },
      { label: "PDF", href: "https://arxiv.org/pdf/2603.14288" },
      {
        label: "SSRN",
        href: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6416881",
      },
      { label: "RePEc / IDEAS", href: "https://ideas.repec.org/p/arx/papers/2603.14288.html" },
      {
        label: "Project homepage",
        href: "https://allenh16.github.io/agentic-factor-investing/",
      },
    ],
  },
];

const RESEARCHERS: { name: string; affiliation: string; links: Link[]; note?: string }[] = [
  {
    name: "Yikuan Huang",
    affiliation: "Division of Emerging Interdisciplinary Areas, HKUST · HKUST (Guangzhou)",
    links: [
      {
        label: "Project homepage",
        href: "https://allenh16.github.io/agentic-factor-investing/",
      },
    ],
  },
  {
    name: "Zheqi Fan",
    affiliation: "Division of Emerging Interdisciplinary Areas, HKUST · Thrust of FinTech, HKUST (Guangzhou)",
    links: [
      { label: "Personal site", href: "https://sites.google.com/view/zheqifan/home/" },
      {
        label: "Google Scholar",
        href: "https://scholar.google.com/citations?user=K3D1VI8AAAAJ&hl=en",
      },
      { label: "ResearchGate", href: "https://www.researchgate.net/profile/Zheqi-Fan-3" },
    ],
  },
  {
    name: "Kaiqi Hu",
    affiliation: "Rutgers Business School",
    links: [],
  },
  {
    name: "Yifan Ye",
    affiliation: "Beijing Normal–Hong Kong Baptist University (BNBU)",
    links: [],
  },
];

function LinkRow({ links }: { links: Link[] }) {
  if (links.length === 0) {
    return (
      <p className="mt-2 text-[11px] text-muted">
        no profile link — none could be confirmed as this person rather than a namesake.
      </p>
    );
  }
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] uppercase tracking-widest">
      {links.map((link) => (
        <a
          key={link.href}
          href={link.href}
          target="_blank"
          rel="noreferrer noopener"
          className="border border-line px-2 py-[3px] text-grey transition-colors hover:border-magenta hover:text-magenta"
        >
          {link.label}
        </a>
      ))}
    </div>
  );
}

export default function ResearchPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-12">
      <div>
        <Label>research</Label>
        <h1 className="mt-3 font-display text-lg tracking-wide">what this is built on</h1>
        <p className="mt-4 max-w-2xl text-muted">
          GODGOD is an implementation of a published idea, not an invention. The work below
          is what it takes from: an LLM agent that proposes falsifiable hypotheses, and a
          deterministic engine that decides whether they hold.
        </p>
        <p className="mt-3 max-w-2xl text-muted">
          The papers report returns. This system does not trade, has no wallet execution path
          in any configuration, and reproduces none of those results — it borrows the method,
          not the outcome.
        </p>
      </div>

      <Section title="foundation" note="the architecture this system implements">
        <div className="space-y-12">
          {PAPERS.map((paper) => (
            <article key={paper.title}>
              <h2 className="font-display text-[15px] leading-relaxed tracking-wide text-bone">
                {paper.title}
              </h2>
              <p className="mt-2 text-[11px] uppercase tracking-widest text-grey">
                {paper.authors} · {paper.year}
              </p>
              <p className="mt-1 text-[11px] text-muted">{paper.venue}</p>

              <blockquote className="mt-4 border-l border-line pl-4 text-muted">
                {paper.abstract}
              </blockquote>

              <p className="mt-4 text-bone">{paper.why}</p>

              <LinkRow links={paper.links} />
            </article>
          ))}
        </div>
      </Section>

      <Section title="researchers">
        <div className="space-y-8">
          {RESEARCHERS.map((person) => (
            <article key={person.name}>
              <h3 className="font-display text-[13px] tracking-wide text-bone">
                {person.name}
              </h3>
              <p className="mt-1 text-[11px] text-muted">{person.affiliation}</p>
              <LinkRow links={person.links} />
            </article>
          ))}
        </div>
      </Section>

      <Section title="on these links" note="how this page is maintained">
        <p className="text-muted">
          Every arXiv and RePEc link here was fetched and read. Affiliations come from the
          papers themselves rather than from a search result.
        </p>
        <p className="mt-3 text-muted">
          The SSRN and ResearchGate links answer automated requests with 403, so they were
          confirmed against an index listing the matching title and authors rather than by
          opening them. That is a weaker check and it is worth saying so — everything else
          on this page was read directly.
        </p>
        <p className="mt-3 text-muted">
          Two researchers are listed without a profile link. Searching returns accounts with
          matching names, and none could be confirmed as the same person — a plausible wrong
          link is worse than a missing one, and on a page about not fabricating sources it
          would be the most damaging thing here.
        </p>
        <p className="mt-3 text-[11px] text-muted">
          Found an error, or a profile that should be listed? The repository is public and
          takes issues.
        </p>
      </Section>
    </div>
  );
}
