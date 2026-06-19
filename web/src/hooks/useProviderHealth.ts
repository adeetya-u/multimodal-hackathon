import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/apiBase";

export type CheckStatus = "pass" | "fail" | "skip" | "warn";

export interface ProviderCheck {
  name: string;
  status: CheckStatus;
  detail: string;
  latency_ms?: number | null;
  required?: boolean;
}

export interface ProviderHealthResult {
  ok: boolean;
  voice_ready: boolean;
  required_failed: string[];
  checks: ProviderCheck[];
  checked_at: number;
  agent_in_room?: boolean;
  case_id?: string;
}

const LABELS: Record<string, string> = {
  case_store: "Case store",
  nebius: "Nebius LLM",
  vapi: "Vapi voice",
  insforge: "Insforge storage",
  unsiloed: "Unsiloed PDF",
  moss_cloud: "MOSS cloud",
  moss_local: "MOSS local index",
  minimax: "MiniMax compaction",
  case_artifacts: "Case artifacts",
  case_bootstrap: "Case bootstrap",
};

export function checkLabel(name: string): string {
  return LABELS[name] ?? name;
}

export function useProviderHealth(caseId: string | null, enabled: boolean) {
  const [result, setResult] = useState<ProviderHealthResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    async (deep = false) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (caseId) params.set("case_id", caseId);
        if (!deep) params.set("deep", "false");
        const path = caseId
          ? `/api/cases/${caseId}/voice-readiness`
          : `/api/health/providers?${params}`;
        const res = await apiFetch(path);
        if (!res.ok) throw new Error(await res.text());
        setResult((await res.json()) as ProviderHealthResult);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Health check failed");
      } finally {
        setLoading(false);
      }
    },
    [caseId],
  );

  useEffect(() => {
    if (!enabled) return;
    void refresh(false);
  }, [enabled, refresh]);

  return { result, loading, error, refresh };
}

export function useProviderHealthPoll(
  caseId: string | null,
  enabled: boolean,
  pollMs = 5000,
) {
  const state = useProviderHealth(caseId, enabled);

  useEffect(() => {
    if (!enabled || pollMs <= 0) return;
    const id = window.setInterval(() => void state.refresh(false), pollMs);
    return () => window.clearInterval(id);
  }, [enabled, pollMs, state.refresh]);

  return state;
}
