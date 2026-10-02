import ts from "typescript";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
const violations = [];
function scan(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) scan(p);
    else if (/\.[jt]sx?$/.test(p)) {
      const source = ts.createSourceFile(
        p,
        readFileSync(p, "utf8"),
        ts.ScriptTarget.Latest,
        true,
        p.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
      );
      function visit(n) {
        const jsx =
          (ts.isJsxOpeningElement(n) || ts.isJsxSelfClosingElement(n)) &&
          ["select", "option", "datalist"].includes(n.tagName.getText(source));
        const factory =
          ts.isCallExpression(n) &&
          /^(React\.)?createElement$/.test(n.expression.getText(source)) &&
          n.arguments[0] &&
          ts.isStringLiteral(n.arguments[0]) &&
          ["select", "option", "datalist"].includes(n.arguments[0].text);
        if (jsx || factory)
          violations.push(
            `${p}:${source.getLineAndCharacterOfPosition(n.getStart()).line + 1}: no-native-choice-control`,
          );
        ts.forEachChild(n, visit);
      }
      visit(source);
    }
  }
}
scan("src");
if (violations.length) {
  console.error(violations.join("\n"));
  process.exit(1);
}
console.log("no-native-choice-control: passed");
