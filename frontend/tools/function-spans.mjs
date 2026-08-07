// Emit one JSON record per function in the files named on the command line.
//
// Uses the TypeScript compiler already in devDependencies rather than counting
// braces: JSX, arrow functions assigned to consts, methods in object literals
// and nested callbacks all have to be found, and a regex finds three of those
// four badly.
//
//   node frontend/tools/function-spans.mjs <file> [file...]
//
// A span is reported for anything with a body, named by its nesting path so
// two `accept` callbacks in one file stay distinguishable.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const ts = createRequire(import.meta.url)("typescript");

const KINDS = new Set([
  ts.SyntaxKind.FunctionDeclaration,
  ts.SyntaxKind.FunctionExpression,
  ts.SyntaxKind.ArrowFunction,
  ts.SyntaxKind.MethodDeclaration,
  ts.SyntaxKind.GetAccessor,
  ts.SyntaxKind.SetAccessor,
  ts.SyntaxKind.Constructor
]);

/** The name a reader would use: the declaration it is attached to, if any. */
function nameOf(node) {
  if (node.name) return node.name.getText();
  const parent = node.parent;
  if (!parent) return "<anonymous>";
  if (ts.isVariableDeclaration(parent) || ts.isPropertyAssignment(parent)) {
    return parent.name.getText();
  }
  if (ts.isPropertyDeclaration(parent)) return parent.name.getText();
  if (ts.isCallExpression(parent) && parent.expression) {
    return `<arg of ${parent.expression.getText().slice(0, 40)}>`;
  }
  return "<anonymous>";
}

const spans = [];
for (const file of process.argv.slice(2)) {
  const text = readFileSync(file, "utf8");
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.ES2022, true);
  const walk = (node, trail) => {
    let next = trail;
    if (KINDS.has(node.kind)) {
      const start = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
      const end = source.getLineAndCharacterOfPosition(node.getEnd()).line + 1;
      next = [...trail, nameOf(node)];
      spans.push({
        file,
        path: next.join(" > "),
        start_line: start,
        end_line: end,
        lines: end - start + 1
      });
    }
    ts.forEachChild(node, child => walk(child, next));
  };
  walk(source, []);
}
process.stdout.write(`${JSON.stringify(spans)}\n`);
