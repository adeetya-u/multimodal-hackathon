import type { TranscriptTurn } from "./useVapiORSession";

export function isVoicePipelineReady(
  agentResponsive: boolean,
  bootstrapAck: boolean,
  micActive: boolean,
): boolean {
  return agentResponsive && bootstrapAck && micActive;
}

export function hasAgentGreeting(turns: TranscriptTurn[]): boolean {
  return turns.some(
    (turn) => turn.role === "agent" && !turn.interim && turn.text.trim().length > 0,
  );
}
