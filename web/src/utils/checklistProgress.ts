import type { ChecklistState } from "../types";

export function forwardMinIndex(checklist: ChecklistState): number {
  const inProgress = checklist.steps.findIndex((s) => s.status === "in_progress");
  if (inProgress >= 0) return inProgress;
  const first = checklist.steps.findIndex((s) => s.status !== "complete");
  return first >= 0 ? first : checklist.steps.length;
}

export function canAdvanceToStep(checklist: ChecklistState, index: number): boolean {
  const step = checklist.steps[index];
  if (!step || step.status === "complete") return false;
  return index >= forwardMinIndex(checklist);
}

export function isStepLocked(checklist: ChecklistState, index: number): boolean {
  return !canAdvanceToStep(checklist, index);
}
