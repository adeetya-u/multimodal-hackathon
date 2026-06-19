import type { ReactNode } from "react";
import type { VitalsSnapshot } from "./useEmulatedVitals";
import { HeartRhythmLine } from "./HeartRhythmLine";

interface VitalCardProps {
  label: string;
  value: string;
  unit?: string;
  tone?: "heart" | "oxygen" | "pressure" | "neutral";
  variant?: "hero" | "compact";
  children?: ReactNode;
}

function VitalCard({
  label,
  value,
  unit,
  tone = "neutral",
  variant = "compact",
  children,
}: VitalCardProps) {
  return (
    <article className={`or-vital-card or-vital-card--${tone} or-vital-card--${variant}`}>
      <span className="or-vital-card-label">{label}</span>
      <p className="or-vital-card-reading">
        <span className="or-vital-card-value">{value}</span>
        {unit && <span className="or-vital-card-unit">{unit}</span>}
      </p>
      {children}
    </article>
  );
}

function meanArterialPressure(sys: number, dia: number): number {
  return Math.round(dia + (sys - dia) / 3);
}

interface Props {
  vitals: VitalsSnapshot;
}

export function VitalsMonitor({ vitals: v }: Props) {
  const map = meanArterialPressure(v.bpSys, v.bpDia);

  return (
    <section className="or-vitals-panel" aria-label="Patient vitals">
      <VitalCard label="HR" value={String(v.hr)} unit="bpm" tone="heart" variant="hero">
        <HeartRhythmLine bpm={v.hr} />
      </VitalCard>
      <div className="or-vitals-grid">
        <VitalCard label="SpO₂" value={String(v.spo2)} unit="%" tone="oxygen" />
        <VitalCard label="NIBP" value={`${v.bpSys}/${v.bpDia}`} unit="mmHg" tone="pressure" />
        <VitalCard label="RR" value={String(v.rr)} unit="/min" />
        <VitalCard label="EtCO₂" value={String(v.etco2)} unit="mmHg" />
        <VitalCard label="Temp" value={v.temp.toFixed(1)} unit="°C" />
        <VitalCard label="MAP" value={String(map)} unit="mmHg" tone="pressure" />
      </div>
    </section>
  );
}
