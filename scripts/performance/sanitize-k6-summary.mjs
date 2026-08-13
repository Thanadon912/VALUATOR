import { readFileSync, writeFileSync } from 'node:fs';

const file = process.argv[2];
if (!file) throw new Error('Usage: sanitize-k6-summary.mjs <summary.json>');

const payload = JSON.parse(readFileSync(file, 'utf8'));
delete payload.setup_data;

const sensitiveKey = /(authorization|api[_-]?key|password|secret|token|cookie|dsn)/i;
const sensitiveValuePatterns = [
  /eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]+)?/g,
  /sb_secret_[A-Za-z0-9_-]+/gi,
  /sk-[A-Za-z0-9]{20,}/g,
  /AKIA[0-9A-Z]{16}/g,
  /postgres(?:ql)?:\/\/[^\s"']+/gi,
  /([?&](?:token|api[_-]?key)=)[^&\s"']+/gi,
];

function sanitize(value) {
  if (Array.isArray(value)) return value.map(sanitize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [
      key,
      sensitiveKey.test(key) ? '[REDACTED]' : sanitize(child),
    ]));
  }
  if (typeof value !== 'string') return value;
  return sensitiveValuePatterns.reduce(
    (text, pattern) => text.replace(pattern, '[REDACTED]'),
    value,
  );
}

writeFileSync(file, `${JSON.stringify(sanitize(payload), null, 2)}\n`, { mode: 0o600 });
