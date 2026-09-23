import { Fragment, type ReactNode } from "react";

/**
 * A deliberately small markdown renderer for assistant turns.
 *
 * The model writes headings, bullets and bold copy the way any chat assistant
 * does, and rendering that as pre-wrapped plain text made good answers look
 * like log output. This covers exactly the subset the assistant actually
 * produces and builds React elements directly — no HTML string is ever
 * constructed, so there is nothing for `dangerouslySetInnerHTML` to do and
 * model output cannot inject markup.
 */

/** `**bold**`, `*italic*`, `` `code` ``, `[text](url)`. */
const INLINE_PATTERN =
  /(\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`|\[[^\]\n]+\]\([^\s)]+\))/g;

/** Only navigable, non-scheme-injecting links survive. */
function safeHref(url: string): string | null {
  try {
    const parsed = new URL(url, "https://hitrendy.invalid");
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let index = 0;

  for (const match of text.matchAll(INLINE_PATTERN)) {
    const token = match[0];
    const start = match.index ?? 0;
    if (start > cursor) {
      nodes.push(text.slice(cursor, start));
    }
    cursor = start + token.length;
    const key = `${keyPrefix}-i${index++}`;

    if (token.startsWith("**") || token.startsWith("__")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("[")) {
      const split = token.indexOf("](");
      const label = token.slice(1, split);
      const href = safeHref(token.slice(split + 2, -1));
      nodes.push(
        href ? (
          <a key={key} href={href} target="_blank" rel="noopener noreferrer">
            {label}
          </a>
        ) : (
          <Fragment key={key}>{label}</Fragment>
        )
      );
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

const HEADING_PATTERN = /^(#{1,3})\s+(.*)$/;
const BULLET_PATTERN = /^\s*[-*•]\s+(.*)$/;
const ORDERED_PATTERN = /^\s*\d+[.)]\s+(.*)$/;
const QUOTE_PATTERN = /^>\s?(.*)$/;
const RULE_PATTERN = /^\s*(?:-{3,}|_{3,}|\*{3,})\s*$/;

export function Markdown({ children }: { children: string }) {
  const lines = children.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];

  // Buffers for the block currently being accumulated. A block ends when the
  // line kind changes or a blank line arrives, which is all the structure this
  // subset needs.
  let paragraph: string[] = [];
  let list: string[] = [];
  let listOrdered = false;
  let quote: string[] = [];
  let code: string[] | null = null;
  let key = 0;

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    const text = paragraph.join(" ");
    blocks.push(<p key={`p${key}`}>{renderInline(text, `p${key++}`)}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (list.length === 0) return;
    const items = list.map((item, i) => (
      <li key={i}>{renderInline(item, `l${key}-${i}`)}</li>
    ));
    blocks.push(
      listOrdered ? (
        <ol key={`l${key++}`}>{items}</ol>
      ) : (
        <ul key={`l${key++}`}>{items}</ul>
      )
    );
    list = [];
  };
  const flushQuote = () => {
    if (quote.length === 0) return;
    const text = quote.join(" ");
    blocks.push(
      <blockquote key={`q${key}`}>
        <p>{renderInline(text, `q${key++}`)}</p>
      </blockquote>
    );
    quote = [];
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
    flushQuote();
  };

  for (const line of lines) {
    if (line.trimStart().startsWith("```")) {
      if (code === null) {
        flushAll();
        code = [];
      } else {
        blocks.push(
          <pre key={`c${key++}`}>
            <code>{code.join("\n")}</code>
          </pre>
        );
        code = null;
      }
      continue;
    }
    if (code !== null) {
      code.push(line);
      continue;
    }

    if (line.trim() === "") {
      flushAll();
      continue;
    }
    if (RULE_PATTERN.test(line)) {
      flushAll();
      blocks.push(<hr key={`h${key++}`} />);
      continue;
    }

    const heading = HEADING_PATTERN.exec(line);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      const Tag = (["h1", "h2", "h3"] as const)[level - 1];
      blocks.push(
        <Tag key={`t${key}`}>{renderInline(heading[2], `t${key++}`)}</Tag>
      );
      continue;
    }

    const quoted = QUOTE_PATTERN.exec(line);
    if (quoted) {
      flushParagraph();
      flushList();
      quote.push(quoted[1]);
      continue;
    }

    const ordered = ORDERED_PATTERN.exec(line);
    const bullet = ordered ? null : BULLET_PATTERN.exec(line);
    if (ordered || bullet) {
      flushParagraph();
      flushQuote();
      const isOrdered = Boolean(ordered);
      if (list.length > 0 && listOrdered !== isOrdered) {
        flushList();
      }
      listOrdered = isOrdered;
      list.push((ordered ?? bullet)![1]);
      continue;
    }

    // A line continuing a list item wraps into it only if indented,
    // otherwise the list ends and regular paragraphs begin.
    if (list.length > 0) {
      if (/^\s{2,}|\t/.test(line)) {
        list[list.length - 1] += ` ${line.trim()}`;
        continue;
      }
      flushList();
    }
    flushQuote();
    paragraph.push(line.trim());
  }

  if (code !== null && code.length > 0) {
    // Unclosed fence: keep the content rather than dropping it.
    blocks.push(
      <pre key={`c${key++}`}>
        <code>{code.join("\n")}</code>
      </pre>
    );
  }
  flushAll();

  return <>{blocks}</>;
}
