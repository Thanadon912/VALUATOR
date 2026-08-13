import { readdirSync, readFileSync } from 'node:fs';
import { basename, join } from 'node:path';

const root = process.argv[2] ?? 'ci-artifacts/performance';
const files = readdirSync(root)
  .filter((name) => name.endsWith('.json') && name !== 'summary-index.json')
  .sort();

function values(metrics, name) {
  const metric = metrics[name];
  return metric?.values ?? metric ?? null;
}

const summaries = files.map((file) => {
  const payload = JSON.parse(readFileSync(join(root, file), 'utf8'));
  const metrics = payload.metrics ?? {};
  const routes = Object.fromEntries(
    Object.entries(metrics)
      .filter(([name]) => name.startsWith('http_req_duration{') && name.includes('route:'))
      .map(([name, metric]) => [name, metric.values ?? metric]),
  );
  return {
    scenario: basename(file, '.json'),
    requests: values(metrics, 'http_reqs'),
    iterations: values(metrics, 'iterations'),
    dropped_iterations: values(metrics, 'dropped_iterations'),
    duration: values(metrics, 'http_req_duration'),
    http_failures: values(metrics, 'http_req_failed'),
    checks: values(metrics, 'checks'),
    business_correctness: values(metrics, 'business_correctness'),
    business_check_failures: values(metrics, 'business_check_failures'),
    valuation_invalid_results: values(metrics, 'valuation_invalid_results'),
    cache_isolation_failures: values(metrics, 'cache_isolation_failures'),
    provider_fallback_count: values(metrics, 'provider_fallback_count'),
    monte_carlo_timeout_count: values(metrics, 'monte_carlo_timeout_count'),
    routes,
  };
});

for (const summary of summaries) {
  for (const field of ['requests', 'duration', 'http_failures', 'checks', 'business_correctness']) {
    if (summary[field] === null) {
      throw new Error(`${summary.scenario}: required k6 metric ${field} is missing`);
    }
  }
}

process.stdout.write(`${JSON.stringify({ generated_at: new Date().toISOString(), summaries }, null, 2)}\n`);
