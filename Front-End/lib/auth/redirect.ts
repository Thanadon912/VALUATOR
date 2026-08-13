import { normalizeTicker } from '@/lib/validation/ticker'

const STOCK_SECTIONS = new Set(['summary', 'news', 'valuation'])

export function safeNextPath(value: FormDataEntryValue | string | null | undefined): string {
  if (typeof value !== 'string') return '/'

  const candidate = value.trim()
  if (candidate === '/' || candidate === '/account') return candidate

  const match = candidate.match(/^\/stocks\/([^/]+)\/(summary|news|valuation)$/)
  if (!match || !STOCK_SECTIONS.has(match[2])) return '/'

  const ticker = normalizeTicker(match[1])
  return ticker ? `/stocks/${ticker}/${match[2]}` : '/'
}

export function authPageHref(path: '/login' | '/register' | '/forgot-password', next: string): string {
  const safeNext = safeNextPath(next)
  return safeNext === '/' ? path : `${path}?next=${encodeURIComponent(safeNext)}`
}
