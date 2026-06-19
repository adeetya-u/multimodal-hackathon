import { Fragment, useMemo, type ReactNode } from "react";

type Block =
  | { type: "p"; text: string }
  | { type: "ul"; items: string[] };

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function parseBlocks(body: string): Block[] {
  const blocks: Block[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push({ type: "ul", items: listItems });
      listItems = [];
    }
  };

  for (const rawLine of body.split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      continue;
    }
    if (line.startsWith("- ") || line.startsWith("* ")) {
      listItems.push(line.slice(2).trim());
      continue;
    }
    flushList();
    blocks.push({ type: "p", text: line });
  }
  flushList();
  return blocks;
}

export function SummaryMarkdown({ body }: { body: string }) {
  const blocks = useMemo(() => parseBlocks(body), [body]);

  return (
    <div className="summary-prose">
      {blocks.map((block, index) => {
        if (block.type === "ul") {
          return (
            <ul key={`ul-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`li-${index}-${itemIndex}`}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        return <p key={`p-${index}`}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
}
