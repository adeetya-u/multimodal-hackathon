import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useIntroRoom } from "../hooks/useIntroRoom";

const PROMPTS = [
  "What are the main indications for total knee replacement?",
  "How do you prevent DVT after knee surgery?",
  "Partial versus total knee replacement - when do you pick each?",
  "What's a typical rehab timeline after TKA?",
] as const;

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StatusPill({
  connection,
  agentConnected,
  demoReady,
  prefetchStatus,
}: {
  connection: string;
  agentConnected: boolean;
  demoReady: boolean;
  prefetchStatus: string;
}) {
  const live = connection === "connected" && agentConnected;
  const tone =
    connection === "error" ? "error" : live ? "live" : demoReady ? "ready" : "idle";
  const label =
    connection === "error"
      ? "Connection failed"
      : live
        ? "Live demo"
        : connection === "connecting"
          ? "Connecting…"
          : prefetchStatus === "warming"
            ? "Warming up…"
            : demoReady
              ? "Demo ready"
              : "Starting…";
  return (
    <span className={`hero-demo-status hero-demo-status--${tone}`}>
      <span className="hero-demo-status-dot" />
      {label}
    </span>
  );
}

/** Moss.dev-style hanging Vapi demo card for the landing hero. */
export function LandingHeroDemo() {
  const room = useIntroRoom();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [promptIdx, setPromptIdx] = useState(0);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [room.transcript]);

  useEffect(() => {
    const id = setInterval(() => setPromptIdx((i) => (i + 1) % PROMPTS.length), 4200);
    return () => clearInterval(id);
  }, []);

  const idle = room.connection === "idle" || room.connection === "error";
  const live = room.connection === "connected" && room.agentConnected;
  const displayTurns = room.transcript.filter((t) => t.text.trim().length > 0);
  const hasUserSpeech = displayTurns.some((t) => t.role === "surgeon");
  const hasTranscript = displayTurns.length > 0;
  const inConversation =
    live &&
    (hasTranscript ||
      hasUserSpeech ||
      room.agentActivity === "searching" ||
      room.agentActivity === "speaking");

  return (
    <div className="hero-demo-wrap">
      <p className="hero-demo-eyebrow">Live voice demo</p>
      <motion.div
        className="hero-demo-float-wrap"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.5 }}
      >
        <div className={`hero-demo-card${inConversation ? " hero-demo-card--conversation" : ""}`}>
        <div className="hero-demo-card-bar">
          <span className="hero-demo-card-label">Scalpel demo agent</span>
          <StatusPill
            connection={room.connection}
            agentConnected={room.agentConnected}
            demoReady={room.demoReady}
            prefetchStatus={room.prefetch.status}
          />
        </div>

        {(!live || !inConversation) && (
        <div className="hero-demo-visual">
          <div className={`hero-demo-ring ${live ? "is-live" : ""}`}>
            <span className="hero-demo-ring-core" />
            <span className="lwave hero-demo-waves">
              {Array.from({ length: 7 }).map((_, i) => (
                <span key={i} style={{ animationDelay: `${i * 0.1}s` }} />
              ))}
            </span>
          </div>
        </div>
        )}

        <div className={`hero-demo-panel${live ? " hero-demo-panel--live" : ""}`}>
          {idle ? (
            <>
              <p className="hero-demo-try-label">Try asking</p>
              <AnimatePresence mode="wait">
                <motion.p
                  key={promptIdx}
                  className="hero-demo-prompt"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.22 }}
                >
                  &ldquo;{PROMPTS[promptIdx]}&rdquo;
                </motion.p>
              </AnimatePresence>
              <button
                className="hero-demo-run"
                onClick={() => void room.connect()}
                disabled={room.connection === "connecting"}
              >
                <MicIcon />
                {room.connection === "connecting" ? "Connecting…" : "Ask Scalpel"}
              </button>
              {room.connection === "error" && room.error && (
                <p className="hero-demo-error">{room.error}</p>
              )}
              <p className="hero-demo-mic-note">Uses your microphone. Nothing is recorded.</p>
            </>
          ) : (
            <>
              <div className="hero-demo-transcript" ref={scrollRef}>
                {displayTurns.length === 0 ? (
                  <div className="hero-demo-waiting">
                    <p className="hero-demo-transcript-hint">
                      {room.agentConnected
                        ? "Connected — ask a general knee or orthopedics question."
                        : "Waiting for Scalpel…"}
                    </p>
                    {room.agentConnected && (
                      <>
                        <p className="hero-demo-try-label">Try asking</p>
                        <p className="hero-demo-prompt hero-demo-prompt--static">
                          &ldquo;{PROMPTS[promptIdx]}&rdquo;
                        </p>
                      </>
                    )}
                  </div>
                ) : (
                  displayTurns.map((turn) => (
                    <div
                      key={turn.id}
                      className={`hero-demo-bubble ${turn.role}${turn.interim ? " interim" : ""}`}
                    >
                      {turn.text}
                    </div>
                  ))
                )}
              </div>
              {room.micError && <p className="hero-demo-error">{room.micError}</p>}
              <button className="hero-demo-end" onClick={() => void room.disconnect()}>
                End demo
              </button>
            </>
          )}
        </div>

        <AnimatePresence>
          {room.wantsPrep && (
            <motion.div
              className="hero-demo-prep"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
            >
              <span>Ready to prep a case?</span>
              <Link className="landing-btn landing-btn-primary" to="/prep" onClick={() => void room.disconnect()}>
                Continue to prep →
              </Link>
            </motion.div>
          )}
        </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
