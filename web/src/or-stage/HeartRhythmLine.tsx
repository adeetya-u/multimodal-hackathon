import { useEffect, useState } from "react";

const SAMPLES = 72;

function nextEcgSample(beatTick: number): number {
  const phase = beatTick % 18;
  if (phase === 0) return 0.5;
  if (phase === 1) return 0.14;
  if (phase === 2) return 0.9;
  if (phase === 3) return 0.2;
  if (phase === 4) return 0.58;
  if (phase === 5) return 0.48;
  return 0.5 + (Math.random() - 0.5) * 0.06;
}

interface Props {
  bpm: number;
}

export function HeartRhythmLine({ bpm }: Props) {
  const [points, setPoints] = useState(() => Array.from({ length: SAMPLES }, () => 0.5));

  useEffect(() => {
    let tick = 0;
    let visible = !document.hidden;
    const intervalMs = Math.max(28, Math.round(60000 / bpm / 18));

    const onVisibility = () => {
      visible = !document.hidden;
    };
    document.addEventListener("visibilitychange", onVisibility);

    const id = window.setInterval(() => {
      if (!visible) return;
      tick += 1;
      setPoints((prev) => [...prev.slice(1), nextEcgSample(tick)]);
    }, intervalMs);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearInterval(id);
    };
  }, [bpm]);

  const width = 100;
  const height = 28;
  const d = points
    .map((y, i) => {
      const x = (i / (SAMPLES - 1)) * width;
      const py = (1 - y) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${py.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      className="or-vital-ecg"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden
    >
      <path d={d} />
    </svg>
  );
}
