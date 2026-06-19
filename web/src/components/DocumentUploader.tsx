import type { IngestionStage } from "../hooks/useCasePrep";
import { DocIcon } from "./icons";

interface Props {
  disabled?: boolean;
  onUpload: (file: File) => void;
  onReparse?: () => void;
  fileName?: string | null;
  uploadingName?: string | null;
  stage?: IngestionStage;
}

function statusMeta(stage: IngestionStage | undefined, isUploading: boolean) {
  if (isUploading) return { label: "Uploading", tone: "active" as const };
  switch (stage) {
    case "parsing":
      return { label: "Parsing", tone: "active" as const };
    case "compacting":
      return { label: "Compacting", tone: "active" as const };
    case "indexing":
      return { label: "Indexing", tone: "active" as const };
    case "ready":
      return { label: "In knowledge base", tone: "ready" as const };
    case "queued":
      return { label: "Queued", tone: "neutral" as const };
    default:
      return { label: "Uploaded", tone: "neutral" as const };
  }
}

function isProcessing(stage: IngestionStage | undefined): boolean {
  return stage === "parsing" || stage === "compacting" || stage === "indexing";
}

export function DocumentUploader({
  disabled,
  onUpload,
  onReparse,
  fileName = null,
  uploadingName = null,
  stage,
}: Props) {
  const displayName = uploadingName || fileName;
  const hasFile = Boolean(displayName);
  const uploading = Boolean(uploadingName);
  const processing = uploading || isProcessing(stage);
  const canReplace = hasFile && !processing && !disabled;
  const status = statusMeta(stage, uploading);

  const pickFile = (file: File | undefined) => {
    if (!file || disabled || processing) return;
    onUpload(file);
  };

  if (!hasFile) {
    return (
      <div
        className={`prep-dropzone ${disabled ? "is-disabled" : ""}`}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          pickFile(e.dataTransfer.files[0]);
        }}
      >
        <div className="prep-dropzone-inner">
          <span className="prep-dropzone-icon" aria-hidden>
            <DocIcon />
          </span>
          <div className="prep-dropzone-copy">
            <p className="prep-dropzone-title">Drop patient chart here</p>
          </div>
          <label className="btn secondary prep-dropzone-btn">
            Choose file
            <input
              type="file"
              accept=".pdf,.txt,.md"
              hidden
              disabled={disabled}
              onChange={(e) => {
                pickFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      </div>
    );
  }

  return (
    <div className={`prep-file-tile ${processing ? "is-processing" : ""} ${stage === "ready" ? "is-ready" : ""}`}>
      <div className="prep-file-tile-main">
        <span className="prep-file-tile-icon" aria-hidden>
          <DocIcon />
        </span>
        <div className="prep-file-tile-content">
          <p className="prep-file-tile-name">{displayName}</p>
          <div className="prep-file-tile-meta">
            <span className={`prep-file-chip prep-file-chip--${status.tone}`}>
              {processing && <span className="document-list-spinner" aria-hidden />}
              {status.label}
            </span>
          </div>
        </div>
      </div>
      {canReplace && (
        <div className="prep-file-actions">
          {onReparse && (
            <button type="button" className="btn secondary prep-file-reparse" onClick={onReparse}>
              Re-parse
            </button>
          )}
          <label className="prep-file-replace">
            Replace file
            <input
              type="file"
              accept=".pdf,.txt,.md"
              hidden
              onChange={(e) => {
                pickFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      )}
    </div>
  );
}
