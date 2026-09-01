import { Wordmark } from "@/components/Mark";
import { getStatus } from "@/lib/status";

/**
 * The claims at the bottom of every page, read from the running system.
 *
 * These three lines were written once and hardcoded: "no financial advice. no
 * execution. failures are published." Every word of that was true, which is
 * exactly what made it dangerous — a sentence that cannot be wrong today is a
 * sentence nobody checks tomorrow, and the day X publishing is switched on the
 * footer would still be describing the deployment that came before it.
 *
 * So the two that can change are read from `/api/status`: what the system is
 * allowed to do with X, and whether anything can sign. The two that cannot —
 * no advice, failures stay up — are properties of the guards and the schema,
 * and they stay written down. If the API is unreachable the claims that depend
 * on it are dropped rather than guessed.
 */
export default async function Footer() {
  const result = await getStatus();
  const mode = result.ok ? result.data.mode : null;

  return (
    <footer className="border-t border-line px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-[10px] uppercase tracking-widest text-muted">
        <Wordmark />
        <span>the autonomous meme researcher</span>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] uppercase tracking-widest text-muted">
        <span>no financial advice</span>
        <span className="select-none text-line">·</span>
        {mode ? (
          <>
            <span>
              {mode.wallet_execution_enabled
                ? "wallet execution enabled"
                : "no wallet, nothing signs"}
            </span>
            <span className="select-none text-line">·</span>
            <span>
              x <span className="text-grey">{mode.x_stage}</span>
            </span>
            <span className="select-none text-line">·</span>
          </>
        ) : null}
        <span>failures stay published</span>
      </div>
    </footer>
  );
}
