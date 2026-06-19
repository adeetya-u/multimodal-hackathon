import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useIntroRoom } from "../hooks/useIntroRoom";

function StatusDot({ connection, agentConnected }: { connection: string; agentConnected: boolean }) {
  const live = connection === "connected" && agentConnected;
  const tone =
    connection === "error"
      ? "error"
      : live
        ? "connected"
        : connection === "connecting" || connection === "connected"
          ? "connecting"
          : "idle";
  const label =
    connection === "error"
      ? "Connection failed"
      : connection === "idle"
        ? "Not connected"
        : live
          ? "Assistant live"
          : connection === "connected"
            ? "Waiting for assistant…"
            : "Connecting…";
  return (
    <span className="intro-status">
      <span className={`intro-status-lamp ${tone}`} />
      {label}
    </span>
  );
}

export function IntroVoicePanel() {
  const room = useIntroRoom();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [room.transcript]);

  const idle = room.connection === "idle" || room.connection === "error";
  const visibleTurns = room.transcript.filter((t) => t.text.trim().length > 0);

  return (
    <div className="intro-panel">
      <div className="intro-panel-head">
        <div className="intro-panel-id">
          <span className={`intro-orb ${room.agentConnected ? "is-live" : ""}`}>
            <span className="lwave">
              {Array.from({ length: 5 }).map((_, i) => (
                <span key={i} style={{ animationDelay: `${i * 0.12}s` }} />
              ))}
            </span>
          </span>
          <div>
            <p className="intro-panel-title">Meet the assistant</p>
            <StatusDot connection={room.connection} agentConnected={room.agentConnected} />
          </div>
        </div>
        {!idle && (
          <button className="intro-panel-end" onClick={() => void room.disconnect()}>
            End
          </button>
        )}
      </div>

      <div className="intro-panel-body">
        {idle ? (
          <div className="intro-panel-empty">
            <p>
              Talk to the voice agent. It'll explain how it preps a case, answers hands-free
              in the OR, and writes the summary — then offer to take you to prep.
            </p>
            <button className="landing-btn landing-btn-primary" onClick={() => void room.connect()}>
              <span className="lwave">
                {Array.from({ length: 4 }).map((_, i) => (
                  <span key={i} style={{ animationDelay: `${i * 0.1}s` }} />
                ))}
              </span>
              Start voice intro
            </button>
            {room.connection === "error" && room.error && (
              <p className="intro-panel-error">{room.error}</p>
            )}
            <p className="intro-panel-mic-note">Uses your microphone. Nothing is recorded.</p>
          </div>
        ) : (
          <>
            <div className="intro-transcript" ref={scrollRef}>
              {visibleTurns.length === 0 ? (
                <p className="intro-transcript-hint">
                  {room.agentConnected
                    ? "Listening… say hello, or ask what it can do."
                    : "Connecting you to the assistant…"}
                </p>
              ) : (
                visibleTurns.map((turn) => (
                  <div key={turn.id} className={`intro-bubble ${turn.role}`}>
                    {turn.text}
                  </div>
                ))
              )}
            </div>
            {room.micError && <p className="intro-panel-error">{room.micError}</p>}
          </>
        )}
      </div>

      <AnimatePresence>
        {room.wantsPrep && (
          <motion.div
            className="intro-prep-cta"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
          >
            <span>Ready when you are.</span>
            <Link className="landing-btn landing-btn-primary" to="/prep" onClick={() => void room.disconnect()}>
              Continue to prep →
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
