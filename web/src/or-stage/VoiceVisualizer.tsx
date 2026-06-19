interface Props {
  active: boolean;
}

export function VoiceVisualizer({ active }: Props) {
  return (
    <div className={`or-voice-viz${active ? " or-voice-viz--active" : ""}`} aria-hidden>
      <div
        className="or-voice-viz-bars"
        style={{ display: "flex", height: "40px", alignItems: "center", gap: "4px" }}
      >
        {active &&
          Array.from({ length: 5 }).map((_, i) => (
            <span
              key={i}
              className="or-voice-viz-bar"
              style={{
                width: 4,
                height: 12 + (i % 3) * 8,
                background: "var(--blue-500, #3b82f6)",
                borderRadius: 2,
                animation: "or-voice-pulse 0.8s ease-in-out infinite",
                animationDelay: `${i * 0.12}s`,
              }}
            />
          ))}
      </div>
    </div>
  );
}
