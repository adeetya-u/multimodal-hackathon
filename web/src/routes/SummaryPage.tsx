import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiFetch } from "../lib/apiBase";
import { AppChrome } from "../components/AppChrome";
import { CheckIcon } from "../components/icons";
import { ScalpelLogo } from "../components/ScalpelLogo";
import { SummaryMarkdown } from "../components/SummaryMarkdown";
import { SummaryTranscript } from "../components/SummaryTranscript";
import { isCaseNotFound, resolveCaseId } from "../utils/caseStorage";

interface SummaryStats {
  steps_completed: number;
  total_steps: number;
  complications: number;
  queries: number;
  events: number;
  transcript_turns?: number;
}

interface SummaryEvent {
  ts: number;
  type: string;
  text: string;
}

interface TranscriptTurn {
  id?: string;
  role: string;
  text: string;
  ts?: number;
}

interface SummaryData {
  status: "in_progress" | "closed";
  case: { case_id: string; patient_id: string; procedure: string };
  patient: { id: string; procedure: string };
  completed_steps?: string[];
  complications?: Array<{ description: string; resolved: boolean; timestamp: number }>;
  mode_transitions?: Array<{ from: string; to: string; trigger: string }>;
  checklist?: { steps: Array<{ id: string; label: string; status?: string }> };
  operative_summary?: string | null;
  closed_at?: number | null;
  events?: SummaryEvent[];
  transcript?: TranscriptTurn[];
  patient_context?: string;
  stats?: SummaryStats;
}

function parseSummarySections(markdown: string): Array<{ title: string; body: string }> {
  return markdown
    .split(/^## /m)
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .map((chunk) => {
      const [title, ...rest] = chunk.split("\n");
      return { title: title.trim(), body: rest.join("\n").trim() };
    });
}

function sectionAccent(title: string): string {
  const key = title.toLowerCase();
  if (key.includes("procedure")) return "accent-procedure";
  if (key.includes("patient") || key.includes("chart")) return "accent-chart";
  if (key.includes("dialogue") || key.includes("transcript")) return "accent-dialogue";
  if (key.includes("complication")) return "accent-complication";
  if (key.includes("follow")) return "accent-followup";
  return "accent-default";
}

function formatClosedAt(ts: number | null | undefined): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatEventTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

function eventTone(type: string): string {
  if (type === "situation") return "warning";
  if (type === "resolution") return "success";
  if (type === "query") return "info";
  if (type === "step") return "step";
  return "neutral";
}

export function SummaryPage() {
  const [params] = useSearchParams();
  const [caseId, setCaseId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [data, setData] = useState<SummaryData | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void resolveCaseId(params.get("case")).then((id) => {
      if (cancelled) return;
      setCaseId(id);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [params]);

  useEffect(() => {
    if (!ready || !caseId) return;
    let cancelled = false;

    void apiFetch(`/api/cases/${caseId}/summary`).then(async (r) => {
      if (cancelled) return;
      if (isCaseNotFound(r)) {
        setCaseId(null);
        return;
      }
      if (!r.ok) return;
      setData((await r.json()) as SummaryData);
    });

    return () => {
      cancelled = true;
    };
  }, [caseId, ready]);

  useEffect(() => {
    if (!caseId || data?.status !== "in_progress") return;
    const id = window.setInterval(() => {
      void apiFetch(`/api/cases/${caseId}/summary`).then(async (r) => {
        if (!r.ok) return;
        setData((await r.json()) as SummaryData);
      });
    }, 4000);
    return () => window.clearInterval(id);
  }, [caseId, data?.status]);

  const sections = useMemo(
    () => (data?.operative_summary ? parseSummarySections(data.operative_summary) : []),
    [data?.operative_summary],
  );

  const exportJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `case-summary-${data.patient.id}.json`;
    a.click();
  };

  const regenerateSummary = async () => {
    if (!caseId || regenerating) return;
    setRegenerating(true);
    try {
      const response = await apiFetch(`/api/cases/${caseId}/summary/generate`, { method: "POST" });
      if (response.ok) {
        setData((await response.json()) as SummaryData);
      }
    } finally {
      setRegenerating(false);
    }
  };

  if (!ready) {
    return (
      <div className="page summary-page">
        <div className="summary-loading">
          <div className="loading-spinner" aria-hidden />
          <p>Loading…</p>
        </div>
      </div>
    );
  }

  if (!caseId) {
    return (
      <div className="page summary-page">
        <div className="summary-empty-card">
          <ScalpelLogo size="lg" className="summary-brand-mark" />
          <h2>No active case</h2>
          <p>Start from prep to open a case, then return here after you end the surgery.</p>
          <Link to="/prep" className="btn filled">Go to prep</Link>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page summary-page">
        <div className="summary-loading">
          <div className="loading-spinner" aria-hidden />
          <p>Loading case…</p>
        </div>
      </div>
    );
  }

  if (data.status === "in_progress") {
    return (
      <div className="page summary-page">
        <header className="summary-hero">
          <AppChrome title="Post-op summary" large />
        </header>
        <div className="summary-waiting-card">
          <ScalpelLogo size="lg" className="summary-brand-mark" />
          <h2>Case in progress</h2>
          <p>
            Say <em>end surgery</em>, <em>surgery is complete</em>, <em>closing is done</em>, or{" "}
            <em>close the case</em> in the OR to generate the summary.
          </p>
          <p className="summary-waiting-meta">
            {data.patient.id}
            <span className="summary-waiting-dot" aria-hidden>·</span>
            {data.patient.procedure}
          </p>
          <Link to={`/or?case=${caseId}`} className="btn filled">Return to OR</Link>
        </div>
      </div>
    );
  }

  const stats = data.stats ?? {
    steps_completed: data.completed_steps?.length ?? 0,
    total_steps: data.checklist?.steps.length ?? 0,
    complications: data.complications?.length ?? 0,
    queries: 0,
    events: data.events?.length ?? 0,
    transcript_turns: data.transcript?.length ?? 0,
  };

  return (
    <div className="page summary-page">
      <header className="summary-hero">
        <AppChrome title="Post-op summary" large />
        <div className="summary-hero-actions">
          <button
            type="button"
            className="btn secondary"
            onClick={() => void regenerateSummary()}
            disabled={regenerating}
          >
            {regenerating ? "Regenerating…" : "Regenerate summary"}
          </button>
          <button type="button" className="btn secondary" onClick={exportJson}>
            Export JSON
          </button>
        </div>
      </header>

      <section className="summary-hero-card">
        <div className="summary-hero-copy">
          <p className="summary-eyebrow">Case closed</p>
          <h1>{data.patient.procedure}</h1>
          <p className="summary-subtitle">
            {data.patient.id}
            {data.closed_at ? ` · ${formatClosedAt(data.closed_at)}` : ""}
          </p>
        </div>
        <div className="summary-stat-grid">
          <div className="summary-stat">
            <span className="summary-stat-value">{stats.steps_completed}/{stats.total_steps}</span>
            <span className="summary-stat-label">Steps</span>
          </div>
          <div className="summary-stat">
            <span className="summary-stat-value">{stats.transcript_turns ?? data.transcript?.length ?? 0}</span>
            <span className="summary-stat-label">Dialogue turns</span>
          </div>
          <div className="summary-stat">
            <span className="summary-stat-value">{stats.events}</span>
            <span className="summary-stat-label">Log events</span>
          </div>
          <div className="summary-stat">
            <span className="summary-stat-value">{stats.complications}</span>
            <span className="summary-stat-label">Complications</span>
          </div>
        </div>
      </section>

      {sections.length > 0 && (
        <section className="summary-section-grid">
          {sections.map((section) => (
            <article
              key={section.title}
              className={`summary-section-card ${sectionAccent(section.title)}`}
            >
              <h2>{section.title}</h2>
              <SummaryMarkdown body={section.body} />
            </article>
          ))}
        </section>
      )}

      {data.transcript && data.transcript.length > 0 && (
        <section className="grouped-section summary-transcript-section">
          <h2 className="section-label">OR transcript</h2>
          <SummaryTranscript turns={data.transcript} />
        </section>
      )}

      {data.checklist && (
        <section className="grouped-section">
          <h2 className="section-label">Checklist</h2>
          <ul className="summary-checklist">
            {data.checklist.steps.map((step) => {
              const done = data.completed_steps?.includes(step.id) || step.status === "complete";
              return (
                <li key={step.id} className={done ? "done" : "pending"}>
                  <CheckIcon className="timeline-check" />
                  <span>{step.label}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {data.events && data.events.length > 0 && (
        <section className="grouped-section">
          <h2 className="section-label">Event log</h2>
          <ol className="summary-timeline">
            {data.events.map((event, index) => (
              <li key={`${event.ts}-${index}`} className={`summary-timeline-item ${eventTone(event.type)}`}>
                <span className="summary-timeline-time">{formatEventTime(event.ts)}</span>
                <span className="summary-timeline-type">{event.type}</span>
                <span className="summary-timeline-text">{event.text}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
