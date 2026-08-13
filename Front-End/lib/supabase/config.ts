type SupabaseConfig = {
  url: string
  publishableKey: string
}

export function hasSupabaseConfig(): boolean {
  return Boolean(
    process.env.SUPABASE_URL?.trim() &&
      process.env.SUPABASE_PUBLISHABLE_KEY?.trim(),
  )
}

export function getSupabaseConfig(): SupabaseConfig {
  const url = process.env.SUPABASE_URL?.trim()
  const publishableKey = process.env.SUPABASE_PUBLISHABLE_KEY?.trim()
  if (!url || !publishableKey) {
    throw new Error(
      'Supabase authentication requires SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY.',
    )
  }

  return { url, publishableKey }
}

export function isGoogleAuthEnabled(): boolean {
  return process.env.GOOGLE_AUTH_ENABLED?.trim().toLowerCase() === 'true'
}
