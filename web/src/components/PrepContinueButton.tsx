import { type CSSProperties } from "react";
import { Link } from "react-router-dom";

interface Props {
  caseId: string | null;
  ingestionReady: boolean;
}

export function PrepContinueButton({ caseId, ingestionReady }: Props) {
  const canContinue = Boolean(caseId && ingestionReady);
  const fillPct = canContinue ? 100 : 0;

  const label = canContinue ? "Continue to OR" : "Prepare case first";
  const hint = canContinue ? null : "Finish case prep to continue";

  return (
    <div className="prep-continue-wrap">
      <Link
        to={canContinue && caseId ? `/or?case=${caseId}` : "#"}
        className={`btn filled prep-continue-btn${canContinue ? "" : " disabled"}`}
        aria-disabled={!canContinue}
        onClick={(e) => {
          if (!canContinue) e.preventDefault();
        }}
      >
        <span
          className="prep-continue-fill"
          style={{ "--p": fillPct } as CSSProperties}
          aria-hidden
        />
        <span className="prep-continue-label">{label}</span>
      </Link>
      {hint && <p className="prep-voice-warmup-hint">{hint}</p>}
    </div>
  );
}
