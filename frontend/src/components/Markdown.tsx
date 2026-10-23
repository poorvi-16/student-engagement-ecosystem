import { Fragment } from "react";

/** Renders the restricted Markdown our content agent writes: ## headings, "- " lists, paragraphs and **bold**. No HTML, no links. */
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>,
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      const items = list;
      blocks.push(
        <ul key={`l${blocks.length}`} className="list-disc space-y-1 pl-6">
          {items.map((li, i) => (
            <li key={i}>{inline(li)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line.startsWith("- ")) {
      list.push(line.slice(2));
      continue;
    }
    flush();
    if (!line) continue;
    if (line.startsWith("## ")) {
      blocks.push(
        <h2 key={blocks.length} className="mt-6 text-xl font-semibold">
          {line.slice(3)}
        </h2>,
      );
    } else {
      blocks.push(<p key={blocks.length}>{inline(line)}</p>);
    }
  }
  flush();
  return <div className="space-y-3 leading-relaxed text-gray-800 dark:text-gray-200">{blocks}</div>;
}
