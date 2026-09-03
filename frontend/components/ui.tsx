import type { ReactNode } from "react";

export function Label({ children }: { children: ReactNode }) {
  return <div className="label">{children}</div>;
}

export function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-line pt-4">
      <div className="flex items-baseline justify-between gap-4">
        <Label>{title}</Label>
        {note ? <span className="text-[10px] text-muted">{note}</span> : null}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function Field({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-b border-line py-2 sm:grid sm:grid-cols-[minmax(0,11rem)_1fr] sm:gap-4">
      <div className="text-muted">{k}</div>
      <div className="min-w-0 break-words">{v ?? "—"}</div>
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  SUPPORTED: "text-amber border-amber/40",
  REJECTED: "text-magenta border-magenta/40",
  CONFIRMED: "text-amber border-amber/40",
  PASS: "text-amber border-amber/40",
  FAIL: "text-magenta border-magenta/40",
  APPROVED: "text-amber border-amber/40",
  PUBLISHED: "text-amber border-amber/40",
  INCONCLUSIVE: "text-muted border-line",
  NEEDS_MORE_DATA: "text-muted border-line",
};

export function Tag({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-muted">—</span>;
  const tone = STATUS_TONE[value.toUpperCase()] ?? "text-bone border-line";
  return (
    <span className={`border px-2 py-[2px] text-[10px] tracking-widest ${tone}`}>
      {value.toUpperCase()}
    </span>
  );
}

export function Disconnected({ error, what }: { error: string; what: string }) {
  return (
    <div className="border border-line p-6">
      <Label>no data</Label>
      <p className="mt-3 max-w-xl text-muted">
        The research API did not answer, so {what} cannot be shown. Nothing is displayed in its
        place: an empty screen is correct, invented numbers are not.
      </p>
      <p className="mt-3 text-[11px] text-muted">{error}</p>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="border border-line p-6 text-muted">{children}</div>;
}

/**
 * A labelled example of an object's shape.
 *
 * Empty pages used to say "nothing yet" and stop, which tells a reader nothing
 * about what the page is for or what would fill it. An example fixes that, and
 * it introduces exactly one risk worth engineering against: being mistaken for
 * a measurement.
 *
 * Three things keep the two apart, and none of them is the reader paying
 * attention. Every example is wrapped in this component, which stamps it. The
 * border is dashed where real rows are solid. And every identifier inside is a
 * DEMO placeholder — the same rule the fixtures follow — so an example can
 * never name a real token or carry a number attached to one.
 */
export function ExampleOf({ what, children }: { what: string; children: ReactNode }) {
  return (
    <figure className="mt-5 border border-dashed border-line/70 p-4">
      <figcaption className="mb-3 flex flex-wrap items-baseline gap-x-3">
        <span className="border border-dashed border-grey px-2 py-[2px] font-display text-[9px] uppercase tracking-[0.2em] text-grey">
          example
        </span>
        <span className="text-[10px] uppercase tracking-widest text-grey">
          what {what} looks like — invented for this page, measured by nothing
        </span>
      </figcaption>
      <div className="text-[11px] text-muted">{children}</div>
    </figure>
  );
}

/**
 * The state a page is in when it has nothing to list.
 *
 * It distinguishes two things a blank page used to merge. `unreachable` means
 * the API never answered — a fact about the deployment. Otherwise the API
 * answered and there are no rows — a fact about the research. They call for
 * different sentences and different reader expectations, and showing the same
 * grey box for both is how a broken backend gets read as an idle system.
 *
 * `needs` is the part that makes the page worth loading: what would actually
 * produce the first row. Every one of them is a real precondition of this
 * system, not encouragement.
 */
export function Nothing({
  what,
  unreachable,
  error,
  because,
  needs,
  children,
}: {
  what: string;
  unreachable?: boolean;
  error?: string;
  because: string;
  needs: string[];
  children?: ReactNode;
}) {
  return (
    <div className="border border-line p-6">
      <Label>{unreachable ? "api unreachable" : `no ${what} yet`}</Label>
      <p className="mt-3 max-w-2xl text-muted">
        {unreachable
          ? `The research API did not answer, so ${what} cannot be listed. Nothing is shown in its place — an empty list is correct here, invented rows are not. What ${what} would look like is below.`
          : because}
      </p>
      {unreachable && error ? (
        <p className="mt-2 font-mono text-[10px] text-grey">{error}</p>
      ) : null}

      <div className="mt-5">
        <div className="text-[10px] uppercase tracking-widest text-muted">
          {unreachable ? "what this page shows" : "what would produce the first one"}
        </div>
        <ul className="mt-2 space-y-1">
          {needs.map((item) => (
            <li key={item} className="flex gap-3 text-[11px] text-muted">
              <span className="text-grey">—</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {children}
    </div>
  );
}

/** A key/value row inside an example. Muted, so it never reads as live data. */
export function ExampleField({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-b border-line/60 py-1.5 sm:grid sm:grid-cols-[minmax(0,10rem)_1fr] sm:gap-4">
      <div className="text-grey">{k}</div>
      <div className="min-w-0 break-words">{v}</div>
    </div>
  );
}
