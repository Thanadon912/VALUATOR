import { after, NextResponse, type NextRequest } from 'next/server'

import { safeNextPath } from '@/lib/auth/redirect'
import { queueWelcomeEmail } from '@/lib/auth/email'
import { getAppBaseUrl } from '@/lib/auth/url'
import { createClient } from '@/lib/supabase/server'
import { hasSupabaseConfig } from '@/lib/supabase/config'

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get('code')
  const next = safeNextPath(request.nextUrl.searchParams.get('next'))
  const destination = request.nextUrl.searchParams.get('recovery') === '1'
    ? `/account/update-password${next === '/' ? '' : `?next=${encodeURIComponent(next)}`}`
    : next
  const redirectOrigin = getAppBaseUrl() ?? request.nextUrl.origin

  if (code && hasSupabaseConfig()) {
    try {
      const supabase = await createClient()
      const { data, error } = await supabase.auth.exchangeCodeForSession(code)
      if (!error) {
        if (request.nextUrl.searchParams.get('recovery') !== '1' && data.user?.id) {
          after(() => queueWelcomeEmail(data.user.id))
        }
        return NextResponse.redirect(new URL(destination, redirectOrigin))
      }
    } catch {
      // Fall through to the safe, user-facing error state below.
    }
  }

  return NextResponse.redirect(
    new URL('/login?authError=confirmation_failed', redirectOrigin),
  )
}
