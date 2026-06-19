import { ChecklistPanel } from "../components/ChecklistPanel";
import { ConnectionBar } from "../components/ConnectionBar";
import { ModePill } from "../components/ModePill";
import { ScalpelLogo } from "../components/ScalpelLogo";
import { CenterStage, useORStage, VitalsMonitor } from "../or-stage";

export function ORPage() {
  const live = useORStage();

  return (
    <div className="or-page-v2">
      <header className="or-toolbar">
        <div className="or-toolbar-left">
          <ScalpelLogo size="xs" className="or-toolbar-logo" />
          <ModePill mode={live.agentMode} />
        </div>
        <p className="or-toolbar-step">
          {live.checklist?.steps.find((s) => s.status === "in_progress")?.label
            ?? live.checklist?.steps.find((s) => s.status === "pending")?.label
            ?? live.currentStep}
        </p>
        <div className="or-toolbar-right">
          <ConnectionBar
            connection={live.connection}
            listening={live.listening}
            agentConnected={live.agentConnected}
            micActive={live.micActive}
            error={live.error ?? live.micError}
            onDisconnect={() => void live.endCase()}
            endingCase={live.endingCase}
            compact
          />
        </div>
      </header>

      <div className="or-stage-body">
        <CenterStage
          agentMode={live.agentMode}
          primaryCard={live.primaryCard}
          transcript={live.transcript}
          voiceActive={live.connection === "connected" && live.listening}
          agentReady={live.agentConnected}
          micActive={live.micActive}
          micError={live.micError}
          connectionError={live.connection === "error" ? live.error : null}
          agentActivity={live.agentActivity}
          answerMeta={live.answerMeta}
          agentResponsive={live.agentResponsive}
          voiceReady={live.voiceReady}
        />

        <aside className="or-stage-checklist-rail">
          <VitalsMonitor vitals={live.vitals} />
          <ChecklistPanel checklist={live.checklist} />
        </aside>
      </div>
    </div>
  );
}
