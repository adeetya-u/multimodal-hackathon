import type { ConnectionState } from "../types";
import { WaveIcon } from "./icons";

interface Props {
  connection: ConnectionState;
  listening: boolean;
  agentConnected?: boolean;
  micActive?: boolean;
  error: string | null;
  onDisconnect: () => void;
  endingCase?: boolean;
  compact?: boolean;
}

export function ConnectionBar({
  connection,
  listening,
  agentConnected = false,
  micActive = false,
  error,
  onDisconnect,
  endingCase = false,
  compact = false,
}: Props) {
  const connectedDetail =
    connection === "connected" && listening
      ? !agentConnected
        ? "Agent joining…"
        : !micActive
          ? "No mic"
          : "Live"
      : "Connected";

  const statusLabel = {
    idle: "Connecting…",
    connecting: "Connecting…",
    connected: connectedDetail,
    error: "Unavailable",
  }[connection];

  return (
    <div className={compact ? "session-bar compact" : "session-bar"}>
      <div className="session-status">
        <span className={`status-lamp ${connection}`} aria-hidden />
        {connection === "connected" && listening && (
          <WaveIcon className="status-wave" aria-hidden />
        )}
        <span className="status-label">{statusLabel}</span>
      </div>

      {connection === "connected" && (
        <div className="session-actions">
          <button
            type="button"
            className="btn text"
            onClick={onDisconnect}
            disabled={endingCase}
          >
            {endingCase ? "Closing…" : "End"}
          </button>
        </div>
      )}

      {error && <p className="banner-error">{error}</p>}
    </div>
  );
}
