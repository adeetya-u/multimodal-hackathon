import { useState } from "react";
import type { RichCard } from "./types";

interface Props {
  card: RichCard;
}

function highlightText(text: string, snippet: string): React.ReactNode {
  if (!snippet) return text;
  const idx = text.toLowerCase().indexOf(snippet.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="or-stage-highlight">{text.slice(idx, idx + snippet.length)}</mark>
      {text.slice(idx + snippet.length)}
    </>
  );
}

function PdfViewer({ pdfUrl, page }: { pdfUrl: string; page: number }) {
  const [pdfError, setPdfError] = useState(false);

  if (pdfError) {
    return (
      <div className="or-stage-pdf-fallback">
        <p>PDF unavailable — see excerpt below.</p>
      </div>
    );
  }

  return (
    <iframe
      className="or-stage-pdf-frame"
      src={`${pdfUrl}#page=${page}`}
      title="Guideline page"
      onError={() => setPdfError(true)}
    />
  );
}

export function GuidelinePage({ card }: Props) {
  const { guideline, excerpt } = card;

  if (guideline?.pdf_url) {
    return (
      <div className="or-stage-guideline-wrap">
        <PdfViewer pdfUrl={guideline.pdf_url} page={guideline.page ?? 1} />
        {guideline.highlight_snippet && (
          <div className="or-stage-guideline-excerpt">
            <span className="or-stage-caption-source">Cited passage</span>
            <p>{highlightText(excerpt, guideline.highlight_snippet)}</p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="or-stage-text-card">
      <p className="or-stage-text-card-body">
        {guideline?.highlight_snippet
          ? highlightText(excerpt, guideline.highlight_snippet)
          : excerpt}
      </p>
    </div>
  );
}
