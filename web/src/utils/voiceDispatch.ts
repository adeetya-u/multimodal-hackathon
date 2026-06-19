/** Client-side voice session helpers for prep/OR warmup. */

import { apiFetch } from "../lib/apiBase";

const BOOTSTRAP_ACK_PREFIX = "voice-bootstrap-ack:";

export function markVoiceBootstrapAck(caseId: string): void {
  try {
    sessionStorage.setItem(`${BOOTSTRAP_ACK_PREFIX}${caseId}`, "1");
  } catch {
    /* private mode */
  }
}

export function isVoiceBootstrapAcked(caseId: string): boolean {
  try {
    return sessionStorage.getItem(`${BOOTSTRAP_ACK_PREFIX}${caseId}`) === "1";
  } catch {
    return false;
  }
}

export async function warmVoiceAgent(caseId: string): Promise<boolean> {
  try {
    const res = await apiFetch(`/api/cases/${caseId}/warm-voice`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}
