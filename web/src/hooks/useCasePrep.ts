import { useCallback, useEffect, useState } from "react";
import { apiFetch, apiUrl } from "../lib/apiBase";
import {
  clearActiveCaseId,
  isCaseNotFound,
  readActiveCaseId,
  setActiveCaseId,
} from "../utils/caseStorage";

export type IngestionStage =
  | "created"
  | "queued"
  | "parsing"
  | "compacting"
  | "indexing"
  | "ready"
  | "error";

export interface CaseFormFields {
  patient_id: string;
  procedure: string;
  manual_notes: string;
  comorbidities: string[];
}

export const DEFAULT_CASE_FIELDS: CaseFormFields = {
  patient_id: "",
  procedure: "",
  manual_notes: "",
  comorbidities: [],
};

export interface CaseRecord {
  case_id: string;
  patient_id: string;
  procedure: string;
  stage: IngestionStage;
  created_at: string;
  updated_at: string;
  documents: string[];
}

interface CaseStatus {
  case: {
    case_id: string;
    stage: IngestionStage;
    patient_id: string;
    procedure: string;
    manual_notes?: string;
    comorbidities?: string[];
    documents: string[];
  };
  preview: {
    compact_context?: Array<{ title: string; summary: string; chunk_type: string }>;
    context_window?: {
      char_budget: number;
      char_used: number;
      patient_pack_count: number;
      reference_pack_count: number;
      prompt_block?: string;
    };
    checklist?: { procedure: string; steps: Array<{ id: string; label: string }> };
  } | null;
}

export function useCasePrep() {
  const [caseId, setCaseId] = useState<string | null>(() => readActiveCaseId());
  const [caseReady, setCaseReady] = useState(false);
  const [status, setStatus] = useState<CaseStatus | null>(null);
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deletingCaseId, setDeletingCaseId] = useState<string | null>(null);
  const [uploadingFile, setUploadingFile] = useState<string | null>(null);

  const refreshCaseHistory = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setCasesLoading(true);
    try {
      const res = await apiFetch("/api/cases");
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as CaseRecord[];
      setCases(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load case history");
    } finally {
      if (!opts?.silent) setCasesLoading(false);
    }
  }, []);

  const syncCaseInHistory = useCallback((snapshot: CaseStatus["case"]) => {
    setCases((prev) => {
      const index = prev.findIndex((item) => item.case_id === snapshot.case_id);
      if (index < 0) {
        return [
          {
            case_id: snapshot.case_id,
            patient_id: snapshot.patient_id,
            procedure: snapshot.procedure,
            stage: snapshot.stage,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            documents: snapshot.documents ?? [],
          },
          ...prev,
        ];
      }
      return prev.map((item) =>
        item.case_id === snapshot.case_id
          ? {
              ...item,
              patient_id: snapshot.patient_id,
              procedure: snapshot.procedure,
              stage: snapshot.stage,
              documents: snapshot.documents ?? item.documents,
            }
          : item,
      );
    });
  }, []);

  useEffect(() => {
    void refreshCaseHistory();
  }, [refreshCaseHistory]);

  const endActiveCase = useCallback(() => {
    setCaseId(null);
    setStatus(null);
    setError(null);
    clearActiveCaseId();
  }, []);

  useEffect(() => {
    const stored = readActiveCaseId();
    if (!stored) {
      setCaseId(null);
      setCaseReady(true);
      return;
    }
    void apiFetch(`/api/cases/${stored}`).then((res) => {
      if (isCaseNotFound(res)) {
        endActiveCase();
      } else {
        setCaseId(stored);
      }
      setCaseReady(true);
    });
  }, [endActiveCase]);

  const pollStatus = useCallback(
    async (id: string) => {
      const res = await apiFetch(`/api/cases/${id}/status`);
      if (isCaseNotFound(res)) {
        endActiveCase();
        return null;
      }
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as CaseStatus;
      setStatus(data);
      syncCaseInHistory(data.case);
      return data;
    },
    [endActiveCase, syncCaseInHistory],
  );

  useEffect(() => {
    if (!caseId || !caseReady) return;

    void pollStatus(caseId);

    const terminal = new Set<IngestionStage>(["ready", "error"]);
    const source = new EventSource(apiUrl(`/api/cases/${caseId}/events`));

    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as CaseStatus;
        setStatus(data);
        syncCaseInHistory(data.case);
        if (terminal.has(data.case.stage)) {
          source.close();
          void refreshCaseHistory({ silent: true });
        }
      } catch {
        /* ignore malformed events */
      }
    };

    source.onerror = () => {
      source.close();
    };

    return () => {
      source.close();
    };
  }, [caseId, caseReady, pollStatus, refreshCaseHistory, syncCaseInHistory]);

  const syncCaseDetails = useCallback(
    async (id: string, payload: CaseFormFields) => {
      const res = await apiFetch(`/api/cases/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (isCaseNotFound(res)) {
        endActiveCase();
        return false;
      }
      if (!res.ok) throw new Error(await res.text());
      await pollStatus(id);
      return true;
    },
    [endActiveCase, pollStatus],
  );

  const createNewCase = useCallback(
    async (payload: CaseFormFields) => {
      const res = await apiFetch("/api/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setCaseId(data.case_id);
      setActiveCaseId(data.case_id);
      await refreshCaseHistory();
      return data.case_id as string;
    },
    [refreshCaseHistory],
  );

  const selectCase = useCallback(
    async (id: string) => {
      if (id === caseId) return;
      setCaseId(id);
      setActiveCaseId(id);
      setError(null);
      await pollStatus(id);
    },
    [caseId, pollStatus],
  );

  const deleteCase = useCallback(
    async (id: string) => {
      setDeletingCaseId(id);
      setError(null);
      try {
        const res = await apiFetch(`/api/cases/${id}`, { method: "DELETE" });
        if (!res.ok) throw new Error(await res.text());
        if (caseId === id) {
          endActiveCase();
        }
        setCases((prev) => prev.filter((item) => item.case_id !== id));
        await refreshCaseHistory();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to delete case");
      } finally {
        setDeletingCaseId(null);
      }
    },
    [caseId, endActiveCase, refreshCaseHistory],
  );

  const startNewCase = useCallback(
    async (payload: CaseFormFields = DEFAULT_CASE_FIELDS) => {
      setBusy(true);
      setError(null);
      try {
        const id = await createNewCase(payload);
        await pollStatus(id);
        return id;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to create case");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [createNewCase, pollStatus],
  );

  const ensureCase = useCallback(
    async (payload: CaseFormFields) => {
      if (caseId) {
        const synced = await syncCaseDetails(caseId, payload);
        if (synced) return caseId;
      }
      setBusy(true);
      setError(null);
      try {
        return await createNewCase(payload);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to create case");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [caseId, syncCaseDetails, createNewCase],
  );

  const createCase = async (payload: CaseFormFields) => ensureCase(payload);

  const triggerPrepare = useCallback(
    async (id: string) => {
      setStatus((prev) =>
        prev ? { ...prev, case: { ...prev.case, stage: "parsing" } } : prev,
      );
      const res = await apiFetch(`/api/cases/${id}/prepare`, { method: "POST" });
      if (isCaseNotFound(res)) {
        endActiveCase();
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      await pollStatus(id);
    },
    [endActiveCase, pollStatus],
  );

  const isProcessing = (stage: IngestionStage | undefined) =>
    stage === "parsing" || stage === "compacting" || stage === "indexing";

  const uploadFile = async (file: File, caseFields?: CaseFormFields) => {
    setBusy(true);
    setUploadingFile(file.name);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const payload = caseFields ?? DEFAULT_CASE_FIELDS;
      const id = await ensureCase(payload);
      if (!id) return;
      const res = await apiFetch(`/api/cases/${id}/documents`, { method: "POST", body: form });
      if (isCaseNotFound(res)) {
        endActiveCase();
        return;
      }
      if (!res.ok) throw new Error(await res.text());
      const uploaded = (await res.json()) as { filename: string; stage?: string };
      await refreshCaseHistory();
      const nextStage = (uploaded.stage as IngestionStage | undefined) ?? "parsing";
      setStatus((prev) =>
        prev && prev.case.case_id === id
          ? {
              ...prev,
              case: { ...prev.case, documents: [uploaded.filename], stage: nextStage },
            }
          : prev,
      );
      await pollStatus(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploadingFile(null);
      setBusy(false);
    }
  };

  const prepareCase = async (caseFields?: CaseFormFields) => {
    if (isProcessing(status?.case.stage)) return;
    setBusy(true);
    setError(null);
    try {
      const id = caseFields ? await ensureCase(caseFields) : caseId;
      if (!id) return;
      await triggerPrepare(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Prepare failed");
    } finally {
      setBusy(false);
    }
  };

  const reparseChart = useCallback(
    async (caseFields?: CaseFormFields) => {
      if (isProcessing(status?.case.stage)) return;
      setBusy(true);
      setError(null);
      try {
        const id = caseFields ? await ensureCase(caseFields) : caseId;
        if (!id) return;
        if (!status?.case.documents?.length) {
          setError("Upload a patient chart before re-parsing");
          return;
        }
        await triggerPrepare(id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Re-parse failed");
      } finally {
        setBusy(false);
      }
    },
    [caseId, ensureCase, status?.case.documents?.length, status?.case.stage, triggerPrepare],
  );

  const updateChecklistPreview = useCallback((checklist: NonNullable<CaseStatus["preview"]>["checklist"]) => {
    setStatus((prev) =>
      prev
        ? {
            ...prev,
            preview: {
              ...prev.preview,
              checklist,
            },
          }
        : prev,
    );
  }, []);

  return {
    caseId,
    cases,
    casesLoading,
    status,
    error,
    busy,
    deletingCaseId,
    uploadingFile,
    patientFileName: status?.case.documents?.[0] ?? null,
    documents: status?.case.documents ?? [],
    createCase,
    startNewCase,
    selectCase,
    deleteCase,
    refreshCaseHistory,
    syncCaseDetails,
    ensureCase,
    uploadFile,
    prepareCase,
    reparseChart,
    pollStatus,
    endActiveCase,
    updateChecklistPreview,
  };
}
