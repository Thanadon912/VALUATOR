import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

import { getSupabaseConfig, hasSupabaseConfig } from './config'

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request })
  if (!hasSupabaseConfig()) return response

  const { url, publishableKey } = getSupabaseConfig()
  const supabase = createServerClient(url, publishableKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll()
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
        response = NextResponse.next({ request })
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        )
      },
    },
  })

  // This validates (and, when needed, refreshes) the auth token. Keep this call
  // immediately after client construction so refreshed cookies are not lost.
  await supabase.auth.getClaims()

  return response
}
