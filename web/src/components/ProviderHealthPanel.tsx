import { checkLabel, type ProviderCheck, type ProviderHealthResult } from "../hooks/useProviderHealth";

const STATUS_ICON: Record<string, string> = {
  pass: "✓",
  fail: "✗",
  warn: "⚠",
  skip: "–",
};

interface Props {
  result: ProviderHealthResult | null;
  loading?: boolean;
  error?: string | null;
  compact?: boolean;
  onRetry?: () => void;
}

export function ProviderHealthPanel({ result, loading, error, compact, onRetry }: Props) {
  if (loading && !result) {
    return <p className="provider-health provider-health--loading">Checking providers…</p>;
  }

  if (error && !result) {
    return (
      <div className="provider-health provider-health--error">
        <p>{error}</p>
        {onRetry && (
          <button type="button" className="btn text" onClick={onRetry}>
            Retry checks
          </button>
        )}
      </div>
    );
  }

  if (!result) return null;

  const failed = result.checks.filter((c) => c.status === "fail");
  const warns = result.checks.filter((c) => c.status === "warn");

  return (
    <section className={`provider-health${compact ? " provider-health--compact" : ""}`} aria-label="Provider health">
      <div className="provider-health-header">
        <h3 className="provider-health-title">System checks</h3>
        <span className={`provider-health-badge ${result.voice_ready ? "ok" : "bad"}`}>
          {result.voice_ready ? "Voice path OK" : "Voice blocked"}
        </span>
        {onRetry && (
          <button type="button" className="btn text provider-health-retry" onClick={onRetry} disabled={loading}>
            {loading ? "Checking…" : "Re-check"}
          </button>
        )}
      </div>

      {(failed.length > 0 || warns.length > 0) && (
        <p className="provider-health-summary">
          {failed.length > 0 && `${failed.length} failed`}
          {failed.length > 0 && warns.length > 0 && ", "}
          {warns.length > 0 && `${warns.length} warning(s)`}
        </p>
      )}

      <ul className="provider-health-list">
        {result.checks.map((check) => (
          <CheckRow key={check.name} check={check} />
        ))}
      </ul>
    </section>
  );
}

function CheckRow({ check }: { check: ProviderCheck }) {
  return (
    <li className={`provider-health-row status-${check.status}`}>
      <span className="provider-health-icon" aria-hidden>
        {STATUS_ICON[check.status] ?? "?"}
      </span>
      <span className="provider-health-name">{checkLabel(check.name)}</span>
      <span className="provider-health-detail" title={check.detail}>
        {check.detail}
        {check.latency_ms != null && (
          <span className="provider-health-latency"> · {check.latency_ms}ms</span>
        )}
      </span>
    </li>
  );
}
