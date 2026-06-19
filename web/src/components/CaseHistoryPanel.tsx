import { useState } from "react";
import type { CaseRecord } from "../hooks/useCasePrep";
import { TrashIcon } from "./icons";

const STAGE_LABEL: Record<string, string> = {
  created: "New",
  queued: "Queued",
  parsing: "Parsing",
  compacting: "Compacting",
  indexing: "Indexing",
  ready: "Ready",
  error: "Error",
};

function formatWhen(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

interface Props {
  cases: CaseRecord[];
  activeCaseId: string | null;
  loading?: boolean;
  disabled?: boolean;
  deletingCaseId?: string | null;
  onSelect: (caseId: string) => void;
  onDelete: (caseId: string) => void;
  onNewCase: () => void;
}

export function CaseHistoryPanel({
  cases,
  activeCaseId,
  loading = false,
  disabled = false,
  deletingCaseId = null,
  onSelect,
  onDelete,
  onNewCase,
}: Props) {
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const handleDeleteClick = (caseId: string) => {
    if (confirmId === caseId) {
      setConfirmId(null);
      onDelete(caseId);
      return;
    }
    setConfirmId(caseId);
    window.setTimeout(() => {
      setConfirmId((current) => (current === caseId ? null : current));
    }, 4000);
  };

  return (
    <aside className="prep-rail-inner" aria-labelledby="case-history-title">
      <button
        type="button"
        className="btn filled prep-rail-new"
        disabled={disabled}
        onClick={onNewCase}
      >
        New case
      </button>

      <h2 id="case-history-title" className="prep-rail-heading">
        Cases
      </h2>

      <div className="prep-rail-list" role="list">
        {loading && cases.length === 0 && (
          <p className="case-history-empty">Loading…</p>
        )}
        {!loading && cases.length === 0 && (
          <p className="case-history-empty">No cases yet.</p>
        )}
        {cases.map((item) => {
          const active = item.case_id === activeCaseId;
          const stage = STAGE_LABEL[item.stage] ?? item.stage;
          const deleting = deletingCaseId === item.case_id;
          const confirming = confirmId === item.case_id;
          const rowDisabled = disabled || deleting;

          return (
            <div
              key={item.case_id}
              role="listitem"
              className={`case-history-item${active ? " case-history-item--active" : ""}${confirming ? " case-history-item--confirm" : ""}`}
            >
              <button
                type="button"
                className="case-history-row case-history-row--rail"
                disabled={rowDisabled}
                aria-current={active ? "true" : undefined}
                onClick={() => {
                  setConfirmId(null);
                  onSelect(item.case_id);
                }}
              >
                <span className="case-history-main">
                  <span className="case-history-patient">{item.patient_id || "New case"}</span>
                  <span className="case-history-procedure">{item.procedure || "No procedure"}</span>
                </span>
                <span className="case-history-meta case-history-meta--rail">
                  <span className={`case-history-stage case-history-stage--${item.stage}`}>
                    {stage}
                  </span>
                  <span className="case-history-date">{formatWhen(item.created_at)}</span>
                </span>
              </button>

              <button
                type="button"
                className={`case-history-delete${confirming ? " case-history-delete--confirm" : ""}`}
                disabled={rowDisabled}
                aria-label={
                  confirming
                    ? `Confirm delete ${item.patient_id || "case"}`
                    : `Delete ${item.patient_id || "case"}`
                }
                title={confirming ? "Tap again to delete" : "Delete case"}
                onClick={(event) => {
                  event.stopPropagation();
                  handleDeleteClick(item.case_id);
                }}
              >
                {deleting ? (
                  <span className="case-history-delete-spinner" aria-hidden />
                ) : confirming ? (
                  <span className="case-history-delete-label">Delete</span>
                ) : (
                  <TrashIcon className="case-history-delete-icon" />
                )}
              </button>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
