import type { IngestionStage } from "../hooks/useCasePrep";
import { CheckIcon } from "./icons";

const STAGES: { id: IngestionStage; label: string }[] = [
  { id: "created", label: "Created" },
  { id: "parsing", label: "Parse" },
  { id: "compacting", label: "Compact" },
  { id: "indexing", label: "Index" },
  { id: "ready", label: "Ready" },
];

const STAGE_ORDER: IngestionStage[] = [
  "created",
  "queued",
  "parsing",
  "compacting",
  "indexing",
  "ready",
];

interface Props {
  stage: IngestionStage;
  documentCount?: number;
  compact?: boolean;
}

export function IngestionProgress({ stage, documentCount = 0, compact = false }: Props) {
  const idx = STAGE_ORDER.indexOf(stage === "error" ? "created" : stage);

  const stepIndex = (id: IngestionStage) => {
    if (id === "created") return STAGE_ORDER.indexOf("created");
    return STAGE_ORDER.indexOf(id);
  };

  const footnote =
    stage === "queued"
      ? "Starting parse…"
      : stage === "parsing"
        ? `Parsing ${documentCount || "uploaded"} document${documentCount === 1 ? "" : "s"}…`
        : stage === "compacting"
          ? "Compacting extracted context…"
          : stage === "indexing"
            ? "Building search index…"
            : stage === "ready"
              ? "Case ready."
              : null;

  const body = (
    <>
        <ol className={`stepper${compact ? " stepper--compact" : ""}`} aria-label="Ingestion progress">
          {STAGES.map((s, i) => {
            const si = stepIndex(s.id);
            const done = idx > si || (idx === si && stage === "ready") || (s.id === "created" && idx >= 1);
            const active =
              (stage === "queued" && s.id === "parsing") ||
              (idx === si && stage !== "ready" && stage !== "error" && s.id !== "created");
            const waiting = stage === "queued" && s.id === "parsing";
            return (
              <li
                key={s.id}
                className={`stepper-item ${done ? "done" : ""} ${active ? "active" : ""} ${waiting ? "waiting" : ""}`}
              >
                <span className="stepper-dot" aria-hidden>
                  {done ? <CheckIcon className="stepper-check" /> : i + 1}
                </span>
                <span className="stepper-label">{s.label}</span>
                {i < STAGES.length - 1 && <span className="stepper-line" aria-hidden />}
              </li>
            );
          })}
        </ol>
        {footnote && <p className="inset-footnote">{footnote}</p>}
        {stage === "error" && (
          <p className="inset-footnote error-footnote">Processing failed. Check server logs.</p>
        )}
    </>
  );

  if (compact) {
    return (
      <section className="prep-progress-compact" aria-label="Processing">
        <div className="inset-group prep-progress-inset">{body}</div>
      </section>
    );
  }

  return (
    <section className="grouped-section">
      <h2 className="section-label">Processing</h2>
      <div className="inset-group">{body}</div>
    </section>
  );
}
