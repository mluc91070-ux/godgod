import { Disconnected, Empty, Label, Tag } from "@/components/ui";
import { api, fmt, fmtTime } from "@/lib/api";
import type { Anomaly, Observation, Page, Status } from "@/lib/types";

export const dynamic = "force-dynamic";

function Evidence({ anomaly }: { anomaly: Anomaly }) {
  const thresholds = (anomaly.baseline?.thresholds ?? {}) as Record<string, number>;
  const baseline = Object.entries(anomaly.baseline ?? {}).filter(([key]) => key !== "thresholds");

  return (
    <div className="mt-2 border-l border-line pl-4">
      <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest">
        <span className="text-violet">{anomaly.anomaly_type}</span>
        <span className="text-lime">score {fmt(anomaly.score, 2)}</span>
        <span className="text-muted">{anomaly.detector}</span>
      </div>
      <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted">
        {baseline.map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <dt>{key}</dt>
            <dd className="text-bone">{String(value)}</dd>
          </div>
        ))}
        {Object.entries(anomaly.measured ?? {}).map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <dt>{key}</dt>
            <dd className="text-lime">{String(value)}</dd>
          </div>
        ))}
      </dl>
      {Object.keys(thresholds).length ? (
        <p className="mt-1 text-[10px] text-muted">
          thresholds:{" "}
          {Object.entries(thresholds)
            .map(([key, value]) => `${key}=${value}`)
            .join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

export default async function ObservePage() {
  const [observations, anomalies, status] = await Promise.all([
    api<Page<Observation>>("/api/observations?limit=50"),
    api<Page<Anomaly>>("/api/anomalies?limit=200"),
    api<Status>("/api/status"),
  ]);

  if (!observations.ok) return <Disconnected error={observations.error} what="observations" />;

  const byObservation = new Map<string, Anomaly[]>();
  if (anomalies.ok) {
    for (const anomaly of anomalies.data.items) {
      if (!anomaly.observation_id) continue;
      const list = byObservation.get(anomaly.observation_id) ?? [];
      list.push(anomaly);
      byObservation.set(anomaly.observation_id, list);
    }
  }

  const pipeline = status.ok ? status.data.pipeline : null;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-baseline justify-between">
        <Label>observations</Label>
        <span className="text-[10px] text-muted">
          {observations.data.total} recorded
          {anomalies.ok ? ` · ${anomalies.data.total} anomalies` : ""}
        </span>
      </div>

      {pipeline ? (
        <p className="mt-4 text-[11px] text-muted">
          source <span className="text-bone">{pipeline.source}</span> · {pipeline.window_hours}h
          window · {pipeline.detectors.length} deterministic detectors · no model in the loop, so
          every row below was decided by a threshold, not by a judgement.
        </p>
      ) : null}

      <div className="mt-8 space-y-6">
        {observations.data.items.length === 0 ? (
          <Empty>nothing observed yet.</Empty>
        ) : (
          observations.data.items.map((observation) => {
            const found = byObservation.get(observation.id) ?? [];
            return (
              <article key={observation.id} className="border-t border-line pt-4">
                <div className="flex flex-wrap items-center gap-3 text-[10px] uppercase tracking-widest text-muted">
                  <span>#{observation.seq ?? "—"}</span>
                  <Tag value={observation.kind} />
                  <span>{fmtTime(observation.observed_at)}</span>
                  <span>novelty {fmt(observation.novelty_score)}</span>
                  <span>importance {fmt(observation.importance)}</span>
                  <span>confidence {fmt(observation.confidence)}</span>
                  <span className={observation.llm_reviewed ? "text-violet" : ""}>
                    {observation.llm_reviewed ? "model-reviewed" : "filter only"}
                  </span>
                </div>

                <p className="mt-3">{observation.summary}</p>

                {observation.subject_ref ? (
                  <p className="mt-2 break-all text-[11px] text-muted">
                    {observation.subject_type} {observation.subject_ref}
                  </p>
                ) : null}

                {found.map((anomaly) => (
                  <Evidence key={anomaly.id} anomaly={anomaly} />
                ))}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}
