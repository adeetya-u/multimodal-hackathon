import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { CheckIcon, DocIcon, WaveIcon } from "../components/icons";
import { LandingHeroDemo } from "../components/LandingHeroDemo";
import { ScalpelLogo } from "../components/ScalpelLogo";
import "./landing.css";

type IconProps = { className?: string };

function MicIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ShieldIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M12 2l8 3v6c0 5-3.5 8.5-8 11-4.5-2.5-8-6-8-11V5z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9 12l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function BoltIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M13 2L4 14h7l-1 8 9-12h-7z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Waveform({ bars = 18 }: { bars?: number }) {
  return (
    <span className="lwave" aria-hidden>
      {Array.from({ length: bars }).map((_, i) => (
        <span key={i} style={{ animationDelay: `${(i % 6) * 0.12}s` }} />
      ))}
    </span>
  );
}

const STAGES = [
  {
    to: "/prep",
    tab: "Pre-surgery",
    icon: <DocIcon />,
    tone: "tone-blue",
    title: "Prep the case",
    body: "Drop in the chart. It's parsed into a queryable brief and a checklist.",
  },
  {
    to: "/or",
    tab: "OR",
    icon: <WaveIcon />,
    tone: "tone-purple",
    title: "Ask hands-free",
    body: "Grounded answers and a voiced checklist, without touching a screen.",
  },
  {
    to: "/summary",
    tab: "Post-surgery",
    icon: <CheckIcon />,
    tone: "tone-green",
    title: "Hand off cleanly",
    body: "The case rolls up into a structured post-op summary.",
  },
] as const;

const FEATURES = [
  { icon: <MicIcon />, title: "Hands-free", body: "Voice in the sterile field." },
  { icon: <ShieldIcon />, title: "Grounded", body: "From the chart, or it abstains." },
  { icon: <BoltIcon />, title: "Fast", body: "On-device, low-latency retrieval." },
  { icon: <CheckIcon />, title: "Documented", body: "Every case ends with a summary." },
] as const;

function StagePreview({ stage }: { stage: number }) {
  if (stage === 0) {
    const items = ["Confirm consent", "Verify site & side", "Antibiotics given", "Imaging on display"];
    return (
      <div className="ldemo-prep">
        <p className="ldemo-prep-head">Mercy General · Total Knee Arthroplasty</p>
        <ul className="ldemo-checklist">
          {items.map((item, i) => (
            <motion.li
              key={item}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 + i * 0.18 }}
            >
              <span className="ldemo-check"><CheckIcon /></span>
              {item}
            </motion.li>
          ))}
        </ul>
      </div>
    );
  }
  if (stage === 1) {
    return (
      <div className="ldemo-or">
        <motion.div className="ldemo-bubble surgeon" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          “What's the patient's INR?”
        </motion.div>
        <motion.div
          className="ldemo-bubble agent"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <Waveform bars={12} />
          1.1, within range. Last drawn this morning.
        </motion.div>
      </div>
    );
  }
  const stats = [
    { v: "42m", l: "Case time" },
    { v: "8/8", l: "Checklist" },
    { v: "0", l: "Flags" },
    { v: "3", l: "Follow-ups" },
  ];
  return (
    <div className="ldemo-summary">
      {stats.map((s, i) => (
        <motion.div
          key={s.l}
          className="ldemo-stat"
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: i * 0.12 }}
        >
          <span className="ldemo-stat-v">{s.v}</span>
          <span className="ldemo-stat-l">{s.l}</span>
        </motion.div>
      ))}
    </div>
  );
}

export function LandingPage() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setStage((s) => (s + 1) % STAGES.length), 4200);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="landing-nav-inner">
          <span className="landing-brand">
            <ScalpelLogo size="sm" showWordmark />
          </span>
          <nav className="landing-nav-links" aria-label="Sections">
            <a className="landing-nav-link" href="#demo">How it works</a>
            <Link className="landing-nav-cta" to="/prep">Launch app</Link>
          </nav>
        </div>
      </header>

      <section className="landing-hero">
        <div className="landing-hero-grid">
          <div className="landing-hero-copy">
            <motion.span
              className="landing-eyebrow"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <span className="landing-eyebrow-dot" />
              Live in the OR
            </motion.span>
            <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
              Your second brain in the <span className="landing-hero-gradient">operating room</span>
            </motion.h1>
            <motion.p
              className="landing-hero-sub"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.12 }}
            >
              Hands-free voice that preps the case, answers mid-procedure, and writes the summary.
            </motion.p>
            <motion.div
              className="landing-hero-actions"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.18 }}
            >
              <Link className="landing-btn landing-btn-primary" to="/prep">
                Launch app
              </Link>
              <a className="landing-btn landing-btn-secondary" href="#demo">
                How it works
              </a>
            </motion.div>
            <p className="landing-hero-note">Research prototype. Not a medical device.</p>
          </div>

          <LandingHeroDemo />
        </div>
      </section>

      <section className="landing-demo" id="demo">
        <div className="landing-demo-inner">
          <div className="landing-tabs" role="tablist" aria-label="Workflow">
            {STAGES.map((s, i) => (
              <button
                key={s.tab}
                role="tab"
                aria-selected={stage === i}
                className={stage === i ? "landing-tab active" : "landing-tab"}
                onClick={() => setStage(i)}
              >
                <span className={`landing-tab-icon ${s.tone}`}>{s.icon}</span>
                {s.tab}
              </button>
            ))}
          </div>

          <div className="landing-demo-stage">
            <div className="landing-demo-copy">
              <AnimatePresence mode="wait">
                <motion.div
                  key={stage}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.25 }}
                >
                  <p className="landing-demo-step">Step {stage + 1} of 3</p>
                  <h2>{STAGES[stage].title}</h2>
                  <p className="landing-demo-body">{STAGES[stage].body}</p>
                  <Link className="landing-demo-link" to={STAGES[stage].to}>
                    Open {STAGES[stage].tab} →
                  </Link>
                </motion.div>
              </AnimatePresence>
            </div>

            <div className="landing-demo-preview">
              <div className="landing-demo-screen">
                <div className="landing-demo-dots">
                  <span /><span /><span />
                </div>
                <AnimatePresence mode="wait">
                  <motion.div
                    key={stage}
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.98 }}
                    transition={{ duration: 0.28 }}
                    className="landing-demo-screen-body"
                  >
                    <StagePreview stage={stage} />
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-feature-grid">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              className="landing-feature"
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.5 }}
              transition={{ delay: i * 0.06 }}
            >
              <span className="landing-feature-icon">{f.icon}</span>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <motion.div
          className="landing-cta-card"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
        >
          <h2>Prep your first case</h2>
          <div className="landing-hero-actions">
            <Link className="landing-btn landing-btn-onlight" to="/prep">Start a case</Link>
          </div>
        </motion.div>
      </section>

      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <span className="landing-footer-brand">
            <ScalpelLogo size="sm" showWordmark />
          </span>
          <span className="landing-footer-note">Research prototype. Not a medical device.</span>
        </div>
      </footer>

    </div>
  );
}
