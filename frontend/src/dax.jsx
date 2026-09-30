import React from "react";

// Lightweight DAX tokenizer for read-only display. It never rewrites the
// formula: concatenating every token's text reproduces the input exactly.
const TOKEN = new RegExp([
  String.raw`(\/\/[^\n]*|--[^\n]*|\/\*[\s\S]*?\*\/)`, // 1 comment
  String.raw`("(?:[^"]|"")*"?)`, // 2 string
  String.raw`('(?:[^']|'')*'?)`, // 3 quoted table
  String.raw`(\[[^\]]*\]?)`, // 4 column / measure reference
  String.raw`(\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)`, // 5 number
  String.raw`([A-Za-z_][A-Za-z0-9_.]*)(?=\s*\()`, // 6 function
  String.raw`\b(VAR|RETURN|TRUE|FALSE|IN|NOT|AND|OR|DEFINE|EVALUATE|MEASURE|COLUMN|TABLE|ORDER|BY|ASC|DESC|BLANK)\b`, // 7 keyword
].join("|"), "gi");

const CLASSES = [null, "dax-comment", "dax-string", "dax-table", "dax-ref", "dax-number", "dax-fn", "dax-keyword"];

export function highlightDax(source) {
  const text = String(source ?? "");
  const parts = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(TOKEN)) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const group = match.findIndex((value, index) => index > 0 && value !== undefined);
    parts.push(<span key={key++} className={CLASSES[group]}>{match[0]}</span>);
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
