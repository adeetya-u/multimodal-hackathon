import { useEffect, useRef, useState } from "react";
import { CaseHistoryPanel } from "../components/CaseHistoryPanel";
import { ContextPreviewCards } from "../components/ContextPreviewCards";
import { IngestionProgress } from "../components/IngestionProgress";
import { PrepChecklistEditor } from "../components/PrepChecklistEditor";
import { PrepWorkspace } from "../components/PrepWorkspace";
import {
  DEFAULT_CASE_FIELDS,
  type CaseFormFields,
  useCasePrep,
} from "../hooks/useCasePrep";
import { PrepContinueButton } from "../components/PrepContinueButton";
import { AppChrome } from "../components/AppChrome";

export function PrepPage() {
  const {
    caseId,
    cases,
    casesLoading,
    status,
    error,
    busy,
    uploadingFile,
    patientFileName,
    documents,
    uploadFile,
    reparseChart,
    updateChecklistPreview,
    startNewCase,
    selectCase,
    deleteCase,
    deletingCaseId,
  } = useCasePrep();
  const [patientId, setPatientId] = useState(DEFAULT_CASE_FIELDS.patient_id);
  const [procedure, setProcedure] = useState(DEFAULT_CASE_FIELDS.procedure);
  const [notes, setNotes] = useState(DEFAULT_CASE_FIELDS.manual_notes);
  const [comorbidities, setComorbidities] = useState(
    DEFAULT_CASE_FIELDS.comorbidities.join(", "),
  );

  const hydratedCaseRef = useRef<string | null>(null);
  const userEditedRef = useRef(false);

  const caseFields = (): CaseFormFields => ({
    patient_id: patientId,
    procedure,
    manual_notes: notes,
    comorbidities: comorbidities.split(",").map((s) => s.trim()).filter(Boolean),
  });

  useEffect(() => {
    hydratedCaseRef.current = null;
    userEditedRef.current = false;
  }, [caseId]);

  useEffect(() => {
    const c = status?.case;
    if (!c?.case_id) return;

    const processing =
      c.stage === "parsing" || c.stage === "compacting" || c.stage === "indexing" || c.stage === "ready";

    if (hydratedCaseRef.current !== c.case_id) {
      hydratedCaseRef.current = c.case_id;
      userEditedRef.current = false;
      setPatientId(c.patient_id);
      setProcedure(c.procedure);
      setNotes(c.manual_notes ?? "");
      setComorbidities((c.comorbidities ?? []).join(", "));
      return;
    }

    if (processing && !userEditedRef.current) {
      setPatientId(c.patient_id);
      setProcedure(c.procedure);
      setNotes(c.manual_notes ?? "");
      setComorbidities((c.comorbidities ?? []).join(", "));
    }
  }, [status]);

  const resetFormDefaults = () => {
    userEditedRef.current = false;
    setPatientId(DEFAULT_CASE_FIELDS.patient_id);
    setProcedure(DEFAULT_CASE_FIELDS.procedure);
    setNotes(DEFAULT_CASE_FIELDS.manual_notes);
    setComorbidities(DEFAULT_CASE_FIELDS.comorbidities.join(", "));
  };

  const handleNewCase = () => {
    resetFormDefaults();
    void startNewCase(DEFAULT_CASE_FIELDS);
  };

  const stage = status?.case.stage ?? "created";
  const ready = stage === "ready";
  const showProgress = Boolean(documents.length > 0 || stage !== "created");

  return (
    <div className="page prep-page">
      <div className="prep-layout">
        <aside className="prep-rail">
          <CaseHistoryPanel
            cases={cases}
            activeCaseId={caseId}
            loading={casesLoading}
            disabled={busy}
            deletingCaseId={deletingCaseId}
            onSelect={(id) => void selectCase(id)}
            onDelete={(id) => void deleteCase(id)}
            onNewCase={handleNewCase}
          />
          {status?.preview && (
            <ContextPreviewCards preview={status.preview} hideChecklist compact />
          )}
        </aside>

        <div className="prep-main">
          <AppChrome
            title="Pre-op prep"
            large
            actions={
              <PrepContinueButton caseId={caseId} ingestionReady={ready} />
            }
          />

          <div className="prep-main-grid">
            <div className="prep-main-primary">
              <PrepWorkspace
                patientId={patientId}
                procedure={procedure}
                comorbidities={comorbidities}
                notes={notes}
                onPatientId={(v) => {
                  userEditedRef.current = true;
                  setPatientId(v);
                }}
                onProcedure={(v) => {
                  userEditedRef.current = true;
                  setProcedure(v);
                }}
                onComorbidities={(v) => {
                  userEditedRef.current = true;
                  setComorbidities(v);
                }}
                onNotes={(v) => {
                  userEditedRef.current = true;
                  setNotes(v);
                }}
                disabled={busy}
                stage={stage}
                busy={busy}
                patientFileName={patientFileName}
                uploadingFile={uploadingFile}
                onUpload={(file) => void uploadFile(file, caseFields())}
                onReparse={() => void reparseChart(caseFields())}
              />
              {showProgress && (
                <IngestionProgress stage={stage} documentCount={documents.length} compact />
              )}
            </div>

            <div className="prep-main-secondary">
              {caseId && ready && (
                <PrepChecklistEditor
                  caseId={caseId}
                  checklist={
                    status?.preview?.checklist ?? {
                      procedure: procedure || "Surgery",
                      steps: [],
                    }
                  }
                  disabled={busy}
                  onUpdated={updateChecklistPreview}
                />
              )}
            </div>
          </div>

          {error && <p className="banner-error page-banner">{error}</p>}
        </div>
      </div>
    </div>
  );
}
