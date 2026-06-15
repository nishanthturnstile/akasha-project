import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const repoRoot = process.cwd();
const workbookPath =
  process.argv[2] ??
  path.join(
    repoRoot,
    "outputs",
    "akasha-delivery-tracker-refresh",
    "Akasha Delivery Tracker Refresh.xlsx",
  );

const blob = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(blob);

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 12,
  tableMaxCols: 13,
  tableMaxCellChars: 120,
});
console.log(overview.ndjson);

for (const range of [
  "Delivery Roadmap!A1:M40",
  "EOS Feature Mapping!A1:H80",
  "Risks & Decisions!A1:F80",
]) {
  const detail = await workbook.inspect({
    kind: "table",
    range,
    include: "values",
    tableMaxRows: 120,
    tableMaxCols: 13,
    tableMaxCellChars: 200,
    maxChars: 50000,
  });
  console.log(`\n--- ${range} ---`);
  console.log(detail.ndjson);
}
