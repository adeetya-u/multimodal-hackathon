import type { ChecklistState, StepStatus } from "../types";

const STATUS_RANK: Record<StepStatus, number> = {
  pending: 0,
  in_progress: 1,
  complete: 2,
};

/** Keep the furthest step status — API/bootstrap must not revert live OR progress. */
export function mergeChecklistProgress(
  prev: ChecklistState | null,
  incoming: ChecklistState,
): ChecklistState {
  if (!prev || prev.procedure !== incoming.procedure) return incoming;
  const prevById = new Map(prev.steps.map((step) => [step.id, step]));
  return {
    ...incoming,
    updated_at: Math.max(prev.updated_at ?? 0, incoming.updated_at ?? 0),
    steps: incoming.steps.map((step) => {
      const old = prevById.get(step.id);
      if (!old) return step;
      if (STATUS_RANK[step.status] >= STATUS_RANK[old.status]) return step;
      return {
        ...step,
        status: old.status,
        completed_at: old.completed_at ?? step.completed_at,
      };
    }),
  };
}
