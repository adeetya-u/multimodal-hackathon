import { useState, type ReactNode } from "react";

interface Props {
  hideChecklist?: boolean;
  compact?: boolean;
  preview: {
    compact_context?: Array<{ title: string; summary: string; chunk_type: string }>;
    context_window?: {
      char_budget: number;
      char_used: number;
      patient_pack_count: number;
      reference_pack_count: number;
    };
    checklist?: { procedure: string; steps: Array<{ id: string; label: string }> };
  };
}

export function ContextPreviewCards({ preview, hideChecklist = false, compact = false }: Props) {
  const packs = preview.compact_context ?? [];
  const sop = packs.filter((p) => p.chunk_type === "sop");
  const comorbidity = packs.filter((p) => p.chunk_type === "comorbidity");
  const papers = packs.filter((p) => p.chunk_type === "paper");

  return (
    <section
      className={`context-preview${compact ? " context-preview--rail" : ""}`}
      aria-labelledby="context-preview-title"
    >
      <h2 id="context-preview-title" className="context-preview-title">
        Context preview
      </h2>
      <div className="preview-accordion-stack">
        {preview.context_window && (
          <CollapsibleSection
            title="AI context window"
            summary={`${preview.context_window.patient_pack_count + preview.context_window.reference_pack_count} packs · ${Math.round((preview.context_window.char_used / preview.context_window.char_budget) * 100)}% full`}
          >
            <p className="preview-item-body">
              {preview.context_window.patient_pack_count} patient packs +{" "}
              {preview.context_window.reference_pack_count} reference packs (
              {preview.context_window.char_used.toLocaleString()} /{" "}
              {preview.context_window.char_budget.toLocaleString()} chars)
            </p>
          </CollapsibleSection>
        )}
        {sop.length > 0 && (
          <CollapsibleSection title="SOP" summary={`${sop.length} excerpt${sop.length === 1 ? "" : "s"}`}>
            <PreviewItems items={sop} />
          </CollapsibleSection>
        )}
        {comorbidity.length > 0 && (
          <CollapsibleSection
            title="Comorbidities"
            summary={`${comorbidity.length} excerpt${comorbidity.length === 1 ? "" : "s"}`}
          >
            <PreviewItems items={comorbidity} />
          </CollapsibleSection>
        )}
        {papers.length > 0 && (
          <CollapsibleSection
            title="Research"
            summary={`${papers.length} excerpt${papers.length === 1 ? "" : "s"}`}
          >
            <PreviewItems items={papers} />
          </CollapsibleSection>
        )}
        {!hideChecklist && preview.checklist && (
          <CollapsibleSection
            title="Checklist"
            summary={`${preview.checklist.steps.length} steps`}
          >
            <ul className="preview-steps">
              {preview.checklist.steps.map((s) => (
                <li key={s.id}>{s.label}</li>
              ))}
            </ul>
          </CollapsibleSection>
        )}
      </div>
    </section>
  );
}

function CollapsibleSection({
  title,
  summary,
  children,
}: {
  title: string;
  summary: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className={`preview-accordion${open ? " preview-accordion--open" : ""}`}>
      <button
        type="button"
        className="preview-accordion-trigger"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="preview-accordion-leading">
          <span className="preview-accordion-title">{title}</span>
          {!open && <span className="preview-accordion-summary">{summary}</span>}
        </span>
        <span className="preview-accordion-chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && <div className="preview-accordion-body">{children}</div>}
    </div>
  );
}

function PreviewItems({ items }: { items: Array<{ title: string; summary: string }> }) {
  return (
    <>
      {items.map((item, index) => (
        <div key={`${item.title}-${index}`} className="preview-item">
          <p className="preview-item-title">{item.title}</p>
          <p className="preview-item-body">{item.summary}</p>
        </div>
      ))}
    </>
  );
}
