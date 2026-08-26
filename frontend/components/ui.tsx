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
    <div className="grid grid-cols-[minmax(0,11rem)_1fr] gap-4 border-b border-line py-2">
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
