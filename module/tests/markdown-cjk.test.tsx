// @vitest-environment jsdom
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import MarkdownRenderer from "../../vendor/module-ui/src/components/MarkdownRenderer";

function render(content: string) {
  const el = document.createElement("div");
  el.innerHTML = renderToStaticMarkup(<MarkdownRenderer content={content} allowCopy={false} />);
  return el;
}

it("renders Chinese emphasis beside punctuation and adjacent Chinese text", () => {
  const el = render("**东莞台心医院（医学美容科）**更适合重视医院背景的人。\n\n推荐**自然审美**方向。");
  expect([...el.querySelectorAll("strong")].map(node => node.textContent)).toEqual([
    "东莞台心医院（医学美容科）", "自然审美",
  ]);
  expect(el.textContent).not.toContain("**");
});

it("preserves literal Markdown in code and escaped text", () => {
  const el = render("`**医学美容科**`\n\n\\*\\*原文\\*\\*\n\n```text\n**医生（示例）**\n```");
  expect(el.querySelector("strong")).toBeNull();
  expect([...el.querySelectorAll("code")].some(node => node.textContent === "**医学美容科**")).toBe(true);
  expect(el.querySelector("pre")?.textContent).toContain("**医生（示例）**");
  expect(el.textContent).toContain("**原文**");
});
