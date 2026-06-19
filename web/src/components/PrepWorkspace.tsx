import type { IngestionStage } from "../hooks/useCasePrep";
import { DocumentUploader } from "./DocumentUploader";

interface CaseFormProps {
  patientId: string;
  procedure: string;
  comorbidities: string;
  notes: string;
  onPatientId: (v: string) => void;
  onProcedure: (v: string) => void;
  onComorbidities: (v: string) => void;
  onNotes: (v: string) => void;
  disabled?: boolean;
}

interface Props extends CaseFormProps {
  stage: IngestionStage;
  busy: boolean;
  patientFileName: string | null;
  uploadingFile: string | null;
  onUpload: (file: File) => void;
  onReparse?: () => void;
}

export function PrepWorkspace({
  patientId,
  procedure,
  comorbidities,
  notes,
  onPatientId,
  onProcedure,
  onComorbidities,
  onNotes,
  disabled,
  stage,
  busy,
  patientFileName,
  uploadingFile,
  onUpload,
  onReparse,
}: Props) {
  const processing = stage === "parsing" || stage === "compacting" || stage === "indexing";

  return (
    <section className="prep-workspace" aria-labelledby="prep-workspace-title">
      <header className="prep-workspace-header">
        <h2 id="prep-workspace-title" className="prep-workspace-title">
          Case &amp; patient chart
        </h2>
        {processing && (
          <span className="prep-workspace-badge prep-workspace-badge--active" role="status">
            Processing…
          </span>
        )}
      </header>

      <div className="prep-workspace-body">
        <div className="prep-case-panel">
          <h3 className="prep-panel-label">Case details</h3>
          <div className="prep-field-grid">
            <label className="prep-field">
              <span className="prep-field-label">Patient ID</span>
              <input
                value={patientId}
                onChange={(e) => onPatientId(e.target.value)}
                disabled={disabled}
                autoComplete="off"
              />
            </label>
            <label className="prep-field prep-field--wide">
              <span className="prep-field-label">Procedure</span>
              <input
                value={procedure}
                onChange={(e) => onProcedure(e.target.value)}
                disabled={disabled}
              />
            </label>
            <label className="prep-field prep-field--wide">
              <span className="prep-field-label">Comorbidities</span>
              <input
                value={comorbidities}
                onChange={(e) => onComorbidities(e.target.value)}
                disabled={disabled}
                placeholder="Comma-separated"
              />
            </label>
            <label className="prep-field prep-field--wide">
              <span className="prep-field-label">Notes</span>
              <textarea
                value={notes}
                onChange={(e) => onNotes(e.target.value)}
                disabled={disabled}
                rows={2}
                placeholder="Implant preferences, allergies, special considerations…"
              />
            </label>
          </div>
        </div>

        <div className="prep-file-panel">
          <h3 className="prep-panel-label">Patient chart</h3>
          <DocumentUploader
            disabled={busy}
            onUpload={onUpload}
            onReparse={onReparse}
            fileName={patientFileName}
            uploadingName={uploadingFile}
            stage={stage}
          />
        </div>
      </div>
    </section>
  );
}
