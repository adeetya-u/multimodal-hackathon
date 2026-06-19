interface TranscriptTurn {
  id?: string;
  role: string;
  text: string;
  ts?: number;
}

function formatTurnTime(ts: number | undefined): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function SummaryTranscript({ turns }: { turns: TranscriptTurn[] }) {
  const finalTurns = turns.filter((turn) => turn.text.trim());

  if (finalTurns.length === 0) {
    return <p className="summary-transcript-empty">No OR dialogue was recorded.</p>;
  }

  return (
    <ol className="summary-transcript">
      {finalTurns.map((turn, index) => {
        const roleClass = turn.role === "surgeon" ? "surgeon" : "agent";
        return (
          <li key={turn.id ?? `${turn.ts}-${index}`} className={`summary-transcript-turn ${roleClass}`}>
            <div className="summary-transcript-meta">
              <span className="summary-transcript-role">{turn.role === "surgeon" ? "Surgeon" : "Agent"}</span>
              {turn.ts ? <span className="summary-transcript-time">{formatTurnTime(turn.ts)}</span> : null}
            </div>
            <p>{turn.text}</p>
          </li>
        );
      })}
    </ol>
  );
}
