type Bucket = { tokens: number; updatedAt: number }

const buckets = new Map<string, Bucket>()
const activeByGroup = new Map<string, number>()

export type RateLimitDecision = {
  allowed: boolean
  limit: number
  remaining: number
  retryAfter: number
}

function clientIdentifier(request: Request): string {
  if (process.env.TRUST_CLOUDFLARE_HEADERS === 'true') {
    const cloudflareIp = request.headers.get('cf-connecting-ip')?.trim()
    if (cloudflareIp) return cloudflareIp
  }
  return request.headers.get('x-real-ip')?.trim()
    || request.headers.get('x-forwarded-for')?.split(',')[0]?.trim()
    || 'unknown'
}

export function consumeRateLimit(
  request: Request,
  group: string,
  limit: number,
): RateLimitDecision {
  const now = Date.now()
  const key = `${group}:${clientIdentifier(request)}`
  const previous = buckets.get(key) ?? { tokens: limit, updatedAt: now }
  const elapsedSeconds = Math.max(0, now - previous.updatedAt) / 1000
  const tokens = Math.min(limit, previous.tokens + elapsedSeconds * limit / 60)
  const allowed = tokens >= 1
  const updated = { tokens: allowed ? tokens - 1 : tokens, updatedAt: now }
  buckets.set(key, updated)

  if (buckets.size > 4096) {
    const cutoff = now - 10 * 60 * 1000
    for (const [bucketKey, bucket] of buckets) {
      if (bucket.updatedAt < cutoff) buckets.delete(bucketKey)
    }
  }

  return {
    allowed,
    limit,
    remaining: Math.max(0, Math.floor(updated.tokens)),
    retryAfter: Math.max(1, Math.ceil((1 - updated.tokens) * 60 / limit)),
  }
}

export function rateLimitHeaders(decision: RateLimitDecision): HeadersInit {
  return {
    'X-RateLimit-Limit': String(decision.limit),
    'X-RateLimit-Remaining': String(decision.remaining),
  }
}

export function tryAcquireCapacity(group: string, maximum: number): (() => void) | null {
  const active = activeByGroup.get(group) ?? 0
  if (active >= maximum) return null
  activeByGroup.set(group, active + 1)
  let released = false
  return () => {
    if (released) return
    released = true
    activeByGroup.set(group, Math.max(0, (activeByGroup.get(group) ?? 1) - 1))
  }
}
