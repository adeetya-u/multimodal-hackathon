import { useEffect, useState } from "react";

export interface VitalsSnapshot {
  hr: number;
  spo2: number;
  bpSys: number;
  bpDia: number;
  rr: number;
  etco2: number;
  temp: number;
  updatedAt: number;
}

const INITIAL: VitalsSnapshot = {
  hr: 72,
  spo2: 98,
  bpSys: 118,
  bpDia: 72,
  rr: 14,
  etco2: 38,
  temp: 36.7,
  updatedAt: Date.now(),
};

function drift(value: number, min: number, max: number, step: number): number {
  const delta = (Math.random() - 0.5) * 2 * step;
  return Math.round(Math.min(max, Math.max(min, value + delta)));
}

function nextVitals(prev: VitalsSnapshot): VitalsSnapshot {
  return {
    hr: drift(prev.hr, 58, 88, 3),
    spo2: drift(prev.spo2, 95, 100, 1),
    bpSys: drift(prev.bpSys, 100, 135, 4),
    bpDia: drift(prev.bpDia, 60, 85, 3),
    rr: drift(prev.rr, 10, 20, 2),
    etco2: drift(prev.etco2, 32, 45, 2),
    temp: Math.round(drift(prev.temp * 10, 360, 375, 2)) / 10,
    updatedAt: Date.now(),
  };
}

export function useEmulatedVitals(intervalMs = 8000): VitalsSnapshot {
  const [vitals, setVitals] = useState<VitalsSnapshot>(INITIAL);

  useEffect(() => {
    const id = window.setInterval(() => {
      setVitals((prev) => nextVitals(prev));
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);

  return vitals;
}
