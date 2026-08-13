import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = process.env.ALLURE_ARTIFACT_ROOT ?? "ci-artifacts";
const expectedBranch = process.env.CI_BRANCH;
const expectedCommit = process.env.CI_COMMIT;

if (!expectedBranch || !expectedCommit) {
  throw new Error("CI_BRANCH and CI_COMMIT are required for Allure validation");
}

const suites = [
  {
    name: "frontend",
    results: join(root, "allure-results"),
    junit: join(root, "playwright", "test-results", "e2e-junit.xml"),
  },
  {
    name: "backend",
    results: join(root, "backend", "allure-results"),
    junit: join(root, "backend", "backend-junit.xml"),
  },
  {
    name: "supabase",
    results: join(root, "supabase", "allure-results"),
    junit: join(root, "supabase", "supabase-junit.xml"),
  },
];

function junitCount(path) {
  const xml = readFileSync(path, "utf8");
  return [...xml.matchAll(/<testsuite\b[^>]*\btests="(\d+)"/g)]
    .reduce((total, match) => total + Number(match[1]), 0);
}

function resultFiles(path) {
  return readdirSync(path)
    .filter((name) => name.endsWith("-result.json"))
    .map((name) => join(path, name));
}

const results = [];
const counts = {};
const attempts = {};
for (const suite of suites) {
  const files = resultFiles(suite.results);
  const expected = junitCount(suite.junit);
  const parsed = files.map((file) => ({
    suite: suite.name,
    file,
    data: JSON.parse(readFileSync(file, "utf8")),
  }));
  const logicalResults = new Set(parsed.map(({ data }) => data.historyId)).size;
  if (logicalResults !== expected) {
    throw new Error(
      `${suite.name} Allure/JUnit mismatch: ${logicalResults} logical results `
      + `(${files.length} attempts)/${expected}`,
    );
  }
  counts[suite.name] = logicalResults;
  attempts[suite.name] = files.length;
  results.push(...parsed);
}

const requiredFields = ["uuid", "historyId", "testCaseId", "name", "fullName", "status", "start", "stop", "labels"];
for (const { file, data } of results) {
  const missing = requiredFields.filter((field) => data[field] === undefined || data[field] === null || data[field] === "");
  if (missing.length) throw new Error(`${file} is missing Allure fields: ${missing.join(", ")}`);
}

const uuids = new Set();
for (const { file, data } of results) {
  if (uuids.has(data.uuid)) throw new Error(`Duplicate Allure uuid: ${data.uuid} (${file})`);
  uuids.add(data.uuid);
}

for (const key of ["historyId", "testCaseId"]) {
  const seen = new Map();
  for (const { suite, file, data } of results) {
    const identity = `${suite}:${data.fullName}`;
    const previous = seen.get(data[key]);
    if (previous && previous.identity !== identity) {
      throw new Error(
        `Conflicting Allure ${key}: ${data[key]} maps to both ${previous.identity} and ${identity} (${file})`,
      );
    }
    seen.set(data[key], { identity, file });
  }
}

const frontend = results.filter(({ suite }) => suite === "frontend");
const browsers = new Set(frontend.flatMap(({ data }) =>
  (data.parameters ?? []).filter(({ name }) => name === "Project").map(({ value }) => value),
));
for (const browser of ["chromium", "firefox", "webkit"]) {
  if (!browsers.has(browser)) throw new Error(`Allure results are missing browser project: ${browser}`);
}

const approvedEpics = new Set([
  "Authentication",
  "Instrument Workspace",
  "Summary & Fundamentals",
  "News & Evidence",
  "Valuation Overview",
  "DCF",
  "Reverse DCF",
  "Monte Carlo",
  "Financial Data Pipeline",
  "API Contract",
  "Resilience & Degradation",
]);
const requiredLabels = ["epic", "feature", "story", "layer", "priority", "severity", "owner"];
const explicitIds = new Map();
for (const { suite, file, data } of results) {
  const labels = new Map((data.labels ?? []).map(({ name, value }) => [name, value]));
  const labelId = labels.get("testId");
  const explicitId = String(data.testCaseId).startsWith("VAL-")
    ? String(data.testCaseId)
    : String(labelId ?? "").startsWith("VAL-")
      ? String(labelId)
      : null;
  if (!explicitId) continue;

  const missingLabels = requiredLabels.filter((name) => !labels.get(name));
  if (missingLabels.length) {
    throw new Error(`${file} is missing taxonomy labels: ${missingLabels.join(", ")}`);
  }
  if (!approvedEpics.has(labels.get("epic"))) {
    throw new Error(`${file} uses an unapproved Epic: ${labels.get("epic")}`);
  }
  if (labels.get("owner") !== "Thanadon") {
    throw new Error(`${file} uses an unexpected owner: ${labels.get("owner")}`);
  }
  if (explicitId.startsWith("VAL-E2E-SAVED-") && labels.get("feature") !== "Saved Stocks") {
    throw new Error(`${file} must use Saved Stocks as the saved-stock Feature`);
  }

  const identities = explicitIds.get(explicitId) ?? new Set();
  identities.add(`${suite}:${data.fullName}`);
  explicitIds.set(explicitId, identities);
}
for (const [id, identities] of explicitIds) {
  if (identities.size !== 1) {
    throw new Error(`Allure test case ID ${id} maps to multiple tests: ${[...identities].join(", ")}`);
  }
}
for (const prefix of ["VAL-E2E-AUTH-P0-", "VAL-E2E-SAVED-P0-"]) {
  if (![...explicitIds.keys()].some((id) => id.startsWith(prefix))) {
    throw new Error(`Allure results are missing the new regression family: ${prefix}`);
  }
}

function attachmentCount(node) {
  return (node.attachments ?? []).length
    + (node.steps ?? []).reduce((total, step) => total + attachmentCount(step), 0);
}

for (const { file, data } of results.filter(({ data }) => data.status === "passed")) {
  if (attachmentCount(data) > 0) {
    throw new Error(`${file} has attachments even though the test passed`);
  }
}

const categories = JSON.parse(readFileSync(join(root, "allure-results", "categories.json"), "utf8"));
if (!Array.isArray(categories) || categories.length === 0) {
  throw new Error("Allure failure categories are missing");
}
for (const category of categories) {
  if (!category.name || !category.messageRegex || !Array.isArray(category.matchedStatuses)) {
    throw new Error(`Allure category is not conservative and explicit: ${JSON.stringify(category)}`);
  }
}

const properties = Object.fromEntries(
  readFileSync(join(root, "allure-results", "environment.properties"), "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      const separator = line.indexOf("=");
      return [line.slice(0, separator).replaceAll("\\ ", " "), line.slice(separator + 1)];
    }),
);
if (properties.Branch !== expectedBranch || properties.Commit !== expectedCommit) {
  throw new Error(`Allure provenance mismatch: Branch=${properties.Branch}, Commit=${properties.Commit}`);
}
if (["local", "uncommitted"].includes(properties.Branch) || ["local", "uncommitted"].includes(properties.Commit)) {
  throw new Error("Allure CI provenance contains a local fallback value");
}

console.log(JSON.stringify({
  status: "passed",
  counts,
  attempts,
  total: results.length,
  browsers: [...browsers].sort(),
  branch: properties.Branch,
  commit: properties.Commit,
  explicitTestCaseIds: explicitIds.size,
}));
