/**
 * Timed beats for the landing-page 30s Scalpel intro replay (no mic).
 * Used by useScalpel30sDemo and docs/DEMO-30s.md.
 */
import type { TranscriptTurn } from "../utils/transcriptTurns";

export const SCALPEL_30S_DEMO_MS = 30_000;
export const SCALPEL_30S_WELCOME = "Hi, I'm Scalpel. Ask anything about knee surgery!";

export const SCALPEL_30S_Q1 = "What is a TKA?";
export const SCALPEL_30S_A1 =
  "TKA replaces worn knee surfaces with metal and plastic components to relieve pain and restore motion.";

export const SCALPEL_30S_Q2 = "How do you prevent DVT after knee surgery?";
export const SCALPEL_30S_A2 =
  "Early mobilization, mechanical compression, and chemoprophylaxis when indicated — per your protocol.";

export type DemoActivity = "idle" | "searching" | "speaking";

export type Scalpel30sBeat =
  | { atMs: number; type: "connection"; connection: "connecting" | "connected" | "idle" }
  | { atMs: number; type: "activity"; activity: DemoActivity }
  | { atMs: number; type: "turn"; turn: TranscriptTurn }
  | { atMs: number; type: "removeTurn"; id: string }
  | { atMs: number; type: "wantsPrep"; wantsPrep: boolean };

const AGENT_PENDING_ID = "agent-pending";

export const SCALPEL_30S_BEATS: Scalpel30sBeat[] = [
  { atMs: 0, type: "connection", connection: "connecting" },
  { atMs: 700, type: "connection", connection: "connected" },
  {
    atMs: 900,
    type: "turn",
    turn: { id: "welcome", role: "agent", text: SCALPEL_30S_WELCOME, ts: 0 },
  },
  { atMs: 900, type: "activity", activity: "speaking" },
  { atMs: 3200, type: "activity", activity: "idle" },

  {
    atMs: 3800,
    type: "turn",
    turn: { id: "q1-interim", role: "surgeon", text: "What is a", ts: 0, interim: true },
  },
  {
    atMs: 4600,
    type: "turn",
    turn: { id: "q1", role: "surgeon", text: SCALPEL_30S_Q1, ts: 0 },
  },
  { atMs: 4600, type: "removeTurn", id: "q1-interim" },
  { atMs: 5200, type: "activity", activity: "searching" },
  {
    atMs: 5200,
    type: "turn",
    turn: { id: AGENT_PENDING_ID, role: "agent", text: "…", ts: 0, interim: true },
  },
  { atMs: 6800, type: "removeTurn", id: AGENT_PENDING_ID },
  {
    atMs: 6800,
    type: "turn",
    turn: { id: "a1", role: "agent", text: SCALPEL_30S_A1, ts: 0 },
  },
  { atMs: 6800, type: "activity", activity: "speaking" },
  { atMs: 9800, type: "activity", activity: "idle" },

  {
    atMs: 10500,
    type: "turn",
    turn: { id: "q2", role: "surgeon", text: SCALPEL_30S_Q2, ts: 0 },
  },
  { atMs: 11200, type: "activity", activity: "searching" },
  {
    atMs: 11200,
    type: "turn",
    turn: { id: AGENT_PENDING_ID, role: "agent", text: "…", ts: 0, interim: true },
  },
  { atMs: 12800, type: "removeTurn", id: AGENT_PENDING_ID },
  {
    atMs: 12800,
    type: "turn",
    turn: { id: "a2", role: "agent", text: SCALPEL_30S_A2, ts: 0 },
  },
  { atMs: 12800, type: "activity", activity: "speaking" },
  { atMs: 15800, type: "activity", activity: "idle" },

  { atMs: 22000, type: "wantsPrep", wantsPrep: true },
  { atMs: 30000, type: "connection", connection: "idle" },
  { atMs: 30000, type: "activity", activity: "idle" },
  { atMs: 30000, type: "wantsPrep", wantsPrep: false },
];

/** Presenter lines keyed to beat timestamps (for docs / rehearsal). */
export const SCALPEL_30S_NARRATION = [
  { sec: 0, line: "Scalpel is a hands-free voice copilot for the OR." },
  { sec: 1, line: "On the landing demo, surgeons ask general knee questions — no chart yet." },
  { sec: 4, line: "Ask: What is a TKA?" },
  { sec: 7, line: "Scalpel searches reference evidence and answers in one short spoken line." },
  { sec: 11, line: "Follow up: How do you prevent DVT after knee surgery?" },
  { sec: 22, line: "Continue to prep for a patient-specific case with chart upload." },
  { sec: 30, line: "Launch the app to prep, operate, and summarize." },
] as const;
