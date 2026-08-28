"use client";

import type { Problem } from "@/lib/api";

/**
 * One failure, shown the way a person needs it: what went wrong, in plain
 * words, and the things worth trying — Nielsen's ninth heuristic. Every error
 * and every warning in the dashboard renders through this, so there is one
 * place to look and one shape to read.
 *
 * `onRetry` is offered only when retrying is actually safe and useful; the
 * caller decides, because "try again" on a half-finished write is not help.
 */
export default function ErrorBox({
  problem,
  onRetry,
  onDismiss,
  tone = "error",
  retryLabel = "Try again",
}: {
  problem: Problem;
  onRetry?: () => void;
  onDismiss?: () => void;
  tone?: "error" | "warning";
  retryLabel?: string;
}) {
  return (
    <div className={`problem problem-${tone}`} role="alert">
      <div className="problem-head">
        <h3 className="problem-title">{problem.title}</h3>
        {onDismiss && (
          <button className="problem-dismiss" onClick={onDismiss} aria-label="Dismiss">
            ×
          </button>
        )}
      </div>

      <p className="problem-message">{problem.message}</p>

      {problem.fixes.length > 0 && (
        <>
          <p className="problem-fixes-label">Things to try</p>
          <ol className="problem-fixes">
            {problem.fixes.map((fix, i) => (
              <li key={i}>{fix}</li>
            ))}
          </ol>
        </>
      )}

      {onRetry && (
        <button className="problem-retry" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  );
}
