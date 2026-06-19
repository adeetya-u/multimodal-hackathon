import type { RichCard, TranscriptTurn } from "./types";
import { VoiceStage, type AnswerMeta } from "./VoiceStage";

interface Props {
  agentMode: import("../types").AgentMode;
  primaryCard: RichCard | null;
  transcript: TranscriptTurn[];
  voiceActive?: boolean;
  agentReady?: boolean;
  micActive?: boolean;
  micError?: string | null;
  connectionError?: string | null;
  agentActivity?: import("../types").AgentActivity;
  answerMeta?: AnswerMeta | null;
  agentResponsive?: boolean;
  voiceReady?: boolean;
}

export function CenterStage({
  transcript,
  voiceActive = false,
  agentReady = false,
  micActive = false,
  micError = null,
  connectionError = null,
  agentActivity = "idle",
  answerMeta = null,
  agentResponsive = false,
  voiceReady = false,
}: Props) {
  return (
    <div className="or-stage-center">
      <div className="or-voice-stage-wrap">
        <VoiceStage
          turns={transcript}
          voiceActive={voiceActive}
          agentReady={agentReady}
          micActive={micActive}
          micError={micError}
          connectionError={connectionError}
          searching={agentActivity === "searching"}
          speaking={agentActivity === "speaking"}
          answerMeta={answerMeta}
          agentResponsive={agentResponsive}
          voiceReady={voiceReady}
        />
      </div>
    </div>
  );
}
