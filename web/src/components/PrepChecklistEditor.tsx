import { useEffect, useState } from "react";
import { apiFetch } from "../lib/apiBase";

export interface ChecklistDraft {
  procedure: string;
  steps: Array<{ id: string; label: string; aliases?: string[] }>;
}

const MAX_CHECKLIST_STEPS = 10;

interface Props {
  caseId: string;
  checklist: ChecklistDraft;
  disabled?: boolean;
  onUpdated: (checklist: ChecklistDraft) => void;
}

function slugId(label: string): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
  return slug || `step_${Date.now()}`;
}

export function PrepChecklistEditor({ caseId, checklist, disabled, onUpdated }: Props) {
  const [steps, setSteps] = useState(checklist.steps);
  const [newLabel, setNewLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    setSteps(checklist.steps);
  }, [checklist]);

  const persist = async (next: ChecklistDraft) => {
    setSaving(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/cases/${caseId}/checklist`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          procedure: next.procedure,
          steps: next.steps.map((s) => ({
            id: s.id,
            label: s.label,
            aliases: s.aliases ?? [],
          })),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const saved = (await res.json()) as ChecklistDraft;
      setSteps(saved.steps);
      onUpdated(saved);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save checklist");
    } finally {
      setSaving(false);
    }
  };

  const updateLabel = async (stepId: string, label: string) => {
    const trimmed = label.trim();
    if (!trimmed) return;
    const next = {
      ...checklist,
      steps: steps.map((s) => (s.id === stepId ? { ...s, label: trimmed } : s)),
    };
    setSteps(next.steps);
    await persist(next);
  };

  const removeStep = async (stepId: string) => {
    if (steps.length <= 1) return;
    const next = { ...checklist, steps: steps.filter((s) => s.id !== stepId) };
    setSteps(next.steps);
    await persist(next);
  };

  const addStep = async () => {
    const label = newLabel.trim();
    if (!label) return;
    if (steps.length >= MAX_CHECKLIST_STEPS) {
      setError(`Maximum ${MAX_CHECKLIST_STEPS} milestones`);
      return;
    }
    const baseId = slugId(label);
    let id = baseId;
    let n = 2;
    while (steps.some((s) => s.id === id)) {
      id = `${baseId}_${n}`;
      n += 1;
    }
    const next = {
      ...checklist,
      steps: [...steps, { id, label, aliases: [] }],
    };
    setNewLabel("");
    setSteps(next.steps);
    await persist(next);
  };

  const moveStep = async (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= steps.length) return;
    const reordered = [...steps];
    const [item] = reordered.splice(index, 1);
    reordered.splice(target, 0, item!);
    const next = { ...checklist, steps: reordered };
    setSteps(reordered);
    await persist(next);
  };

  const generateFromSop = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/cases/${caseId}/checklist/generate`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const saved = (await res.json()) as ChecklistDraft;
      setSteps(saved.steps);
      onUpdated(saved);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate checklist");
    } finally {
      setGenerating(false);
    }
  };

  const busy = disabled || saving || generating;

  return (
    <section className="prep-checklist-editor">
      <header className="prep-checklist-header">
        <div>
          <h2 className="prep-checklist-title">Operative milestones</h2>
          <p className="prep-checklist-hint">
            Major phases before, during, and after surgery for the OR board. Granular actions
            (incision, tourniquet, etc.) are logged live during the case.
          </p>
        </div>
        <div className="prep-checklist-header-actions">
          {generating && <span className="prep-checklist-saving">Generating…</span>}
          {saving && !generating && <span className="prep-checklist-saving">Saving…</span>}
          <button
            type="button"
            className="btn secondary prep-checklist-generate"
            disabled={busy}
            onClick={() => void generateFromSop()}
          >
            {steps.length === 0 ? "Generate from SOP" : "Regenerate"}
          </button>
        </div>
      </header>

      {steps.length === 0 && (
        <p className="prep-checklist-empty">
          No milestones yet. Upload the chart and run prep, or generate pre/intra/post-op steps from
          the operative SOP.
        </p>
      )}

      <ol className="prep-checklist-steps">
        {steps.map((step, index) => (
          <li key={step.id} className="prep-checklist-row">
            <span className="prep-checklist-index">{index + 1}</span>
            <input
              className="prep-checklist-input"
              value={step.label}
              disabled={busy}
              onChange={(e) =>
                setSteps((prev) =>
                  prev.map((s) => (s.id === step.id ? { ...s, label: e.target.value } : s)),
                )
              }
              onBlur={(e) => void updateLabel(step.id, e.target.value)}
            />
            <div className="prep-checklist-actions">
              <button
                type="button"
                className="prep-checklist-icon-btn"
                disabled={busy || index === 0}
                onClick={() => void moveStep(index, -1)}
                aria-label="Move up"
              >
                ↑
              </button>
              <button
                type="button"
                className="prep-checklist-icon-btn"
                disabled={busy || index === steps.length - 1}
                onClick={() => void moveStep(index, 1)}
                aria-label="Move down"
              >
                ↓
              </button>
              <button
                type="button"
                className="prep-checklist-icon-btn prep-checklist-icon-btn--danger"
                disabled={busy || steps.length <= 1}
                onClick={() => void removeStep(step.id)}
                aria-label="Delete step"
              >
                ×
              </button>
            </div>
          </li>
        ))}
      </ol>

      <div className="prep-checklist-add">
        <input
          className="prep-checklist-input"
          placeholder="Add milestone…"
          value={newLabel}
          disabled={busy}
          onChange={(e) => setNewLabel(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void addStep();
          }}
        />
        <button
          type="button"
          className="btn secondary"
          disabled={busy || !newLabel.trim()}
          onClick={() => void addStep()}
        >
          Add
        </button>
      </div>

      {error && <p className="banner-error">{error}</p>}
    </section>
  );
}
