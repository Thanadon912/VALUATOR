import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { basename, join } from "node:path";

const root = process.env.ALLURE_ARTIFACT_ROOT ?? "ci-artifacts";
const output = join(root, "allure-combined-results");
const sources = [
  { name: "frontend", path: join(root, "allure-results") },
  { name: "backend", path: join(root, "backend", "allure-results") },
  { name: "supabase", path: join(root, "supabase", "allure-results") },
];

// Rebuild the publication directory on every invocation so a retried post step
// cannot retain results from an earlier attempt in the same workspace.
rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });

const owners = new Map();
const uuids = new Map();
const crossSuiteIdentities = {
  historyId: new Map(),
  testCaseId: new Map(),
};
const counts = {};
let totalFiles = 0;
let totalResults = 0;

for (const source of sources) {
  counts[source.name] = { files: 0, results: 0 };
  if (!existsSync(source.path)) continue;

  const entries = readdirSync(source.path, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile()) {
      throw new Error(`Allure source contains an unsupported non-file entry: ${join(source.path, entry.name)}`);
    }

    const fileName = basename(entry.name);
    const existingOwner = owners.get(fileName);
    if (existingOwner) {
      throw new Error(
        `Allure filename collision: ${fileName} appears in both ${existingOwner} and ${source.name}`,
      );
    }

    owners.set(fileName, source.name);
    if (fileName.endsWith("-result.json")) {
      const sourceFile = join(source.path, fileName);
      const result = JSON.parse(readFileSync(sourceFile, "utf8"));
      const requiredFields = [
        "uuid",
        "historyId",
        "testCaseId",
        "name",
        "fullName",
        "status",
        "start",
        "stop",
        "labels",
      ];
      const missing = requiredFields.filter(
        (field) => result[field] === undefined || result[field] === null || result[field] === "",
      );
      if (missing.length > 0) {
        throw new Error(`${sourceFile} is missing Allure fields: ${missing.join(", ")}`);
      }

      const uuidOwner = uuids.get(result.uuid);
      if (uuidOwner) {
        throw new Error(`Allure UUID collision: ${result.uuid} appears in ${uuidOwner} and ${source.name}`);
      }
      uuids.set(result.uuid, source.name);

      for (const key of ["historyId", "testCaseId"]) {
        const previous = crossSuiteIdentities[key].get(result[key]);
        if (previous && previous.source !== source.name) {
          throw new Error(
            `Cross-suite Allure ${key} collision: ${result[key]} appears in ${previous.source} and ${source.name}`,
          );
        }
        crossSuiteIdentities[key].set(result[key], {
          source: source.name,
          fullName: result.fullName,
        });
      }
    }

    copyFileSync(join(source.path, fileName), join(output, fileName));
    counts[source.name].files += 1;
    totalFiles += 1;
    if (fileName.endsWith("-result.json")) {
      counts[source.name].results += 1;
      totalResults += 1;
    }
  }
}

console.log(JSON.stringify({
  status: "assembled",
  output,
  counts,
  totalFiles,
  totalResults,
}));
