import { useEffect, useRef, type CSSProperties } from "react";
import type { ChecklistState } from "../types";
import { CheckIcon } from "./icons";

interface Props {
  checklist: ChecklistState | null;
}

export function ChecklistPanel({ checklist }: Props) {
  const listRef = useRef<HTMLUListElement>(null);

  const completed = checklist?.steps.filter((s) => s.status === "complete").length ?? 0;
  const total = checklist?.steps.length ?? 0;
  const progress = total ? Math.round((completed / total) * 100) : 0;
  const activeStepId =
    checklist?.steps.find((s) => s.status === "in_progress")?.id
    ?? checklist?.steps.find((s) => s.status === "pending")?.id;

  useEffect(() => {
    if (!activeStepId || !listRef.current) return;
    const row = listRef.current.querySelector(`[data-step-id="${activeStepId}"]`);
    row?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeStepId]);

  if (!checklist) {
    return (
      <div className="inset-group loading-state">
        <div className="loading-spinner" aria-hidden />
        <p>Loading…</p>
      </div>
    );
  }

  return (
    <section className="or-checklist-card">
      <header className="or-checklist-header">
        <div className="activity-ring-wrap">
          <div
            className="activity-ring"
            style={{ "--p": progress } as CSSProperties}
            aria-label={`${completed} of ${total} complete`}
          >
            <div className="activity-ring-inner">
              <span className="activity-ring-value">{completed}</span>
              <span className="activity-ring-total">of {total}</span>
            </div>
          </div>
        </div>
        <h1 className="or-procedure-title">{checklist.procedure}</h1>
      </header>

      <ul className="ios-list or-checklist-steps" role="list" ref={listRef}>
        {checklist.steps.map((step, index) => (
          <li
            key={step.id}
            data-step-id={step.id}
            className={`ios-row checklist-row status-${step.status}`}
            aria-current={step.status === "in_progress" ? "step" : undefined}
          >
            <StepRowContent step={step} index={index} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function StepRowContent({
  step,
  index,
}: {
  step: ChecklistState["steps"][0];
  index: number;
}) {
  return (
    <>
      <span className="row-marker" aria-hidden>
        {step.status === "complete" ? (
          <CheckIcon className="row-check" />
        ) : step.status === "in_progress" ? (
          <span className="row-dot active" />
        ) : (
          <span className="row-dot">{index + 1}</span>
        )}
      </span>
      <span className="row-content">
        <span className="row-title">{step.label}</span>
        {step.status === "in_progress" && (
          <span className="row-caption accent">In progress</span>
        )}
        {step.status === "complete" && step.completed_at && (
          <span className="row-caption">
            {new Date(step.completed_at * 1000).toLocaleTimeString([], {
              hour: "numeric",
              minute: "2-digit",
            })}
          </span>
        )}
      </span>
    </>
  );
}
