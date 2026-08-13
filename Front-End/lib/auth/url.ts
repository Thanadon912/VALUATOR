export function getAppBaseUrl(): string | null {
  const configured = process.env.APP_BASE_URL?.trim()
  if (!configured) return null

  try {
    const url = new URL(configured)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
      return null
    }
    if (process.env.APP_ENV === 'production' && url.protocol !== 'https:') {
      return null
    }
    return url.origin
  } catch {
    return null
  }
}
