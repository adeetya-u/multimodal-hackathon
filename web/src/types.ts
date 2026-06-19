export type StepStatus = "pending" | "in_progress" | "complete";
export type AgentMode = "logger" | "query" | "situation" | "summary";

export interface ChecklistStep {
  id: string;
  label: string;
  aliases?: string[];
  status: StepStatus;
  completed_at?: number | null;
}

export interface ChecklistState {
  procedure: string;
  mode: string;
  updated_at: number;
  steps: ChecklistStep[];
}

export interface PatientContext {
  patient_id: string;
  procedure: string;
  summary: string;
}

export type ConnectionState = "idle" | "connecting" | "connected" | "error";
export type AgentActivity = "idle" | "searching" | "speaking";

export interface SituationCard {
  source: string;
  excerpt: string;
  score?: number;
  title?: string;
  pages?: string;
  citation?: string;
  spoken_text?: string;
  confidence?: number;
  chunk_id?: string | null;
  kind?: "guideline" | "text" | "external";
}
