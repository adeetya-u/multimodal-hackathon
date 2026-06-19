import type { AgentMode } from "../types";

const CONFIG: Record<AgentMode, { label: string; dot: string }> = {
  logger: { label: "Logging", dot: "blue" },
  query: { label: "Answering", dot: "green" },
  situation: { label: "Situation", dot: "orange" },
  summary: { label: "Summary", dot: "gray" },
};

interface Props {
  mode: AgentMode;
}

export function ModePill({ mode }: Props) {
  const { label, dot } = CONFIG[mode];
  return (
    <span className={`live-badge live-badge-${dot}`} role="status" aria-live="polite">
      <span className="live-badge-dot" aria-hidden />
      {label}
    </span>
  );
}
