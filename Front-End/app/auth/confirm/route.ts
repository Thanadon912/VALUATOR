import type { EmailOtpType } from '@supabase/supabase-js'
import { after, NextResponse, type NextRequest } from 'next/server'

import { safeNextPath } from '@/lib/auth/redirect'
import { queueWelcomeEmail } from '@/lib/auth/email'
import { getAppBaseUrl } from '@/lib/auth/url'
import { createClient } from '@/lib/supabase/server'
import { hasSupabaseConfig } from '@/lib/supabase/config'

const OTP_TYPES = new Set<EmailOtpType>([
  'signup',
  'invite',
  'magiclink',
  'recovery',
  'email_change',
  'email',
])

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams
  const code = params.get('code')
  const tokenHash = params.get('token_hash')
  const rawType = params.get('type')
  const next = safeNextPath(params.get('next'))
  const redirectOrigin = getAppBaseUrl() ?? request.nextUrl.origin

  if (hasSupabaseConfig()) {
    try {
      const supabase = await createClient()

      if (code) {
        const { data, error } = await supabase.auth.exchangeCodeForSession(code)
        if (!error) {
          if (data.user?.id) after(() => queueWelcomeEmail(data.user.id))
          return NextResponse.redirect(new URL(next, redirectOrigin))
        }
      } else if (tokenHash && rawType && OTP_TYPES.has(rawType as EmailOtpType)) {
        const type = rawType as EmailOtpType
        const { data, error } = await supabase.auth.verifyOtp({
          token_hash: tokenHash,
          type,
        })
        if (!error) {
          const userId = data.user?.id
          if (type !== 'recovery' && userId) {
            after(() => queueWelcomeEmail(userId))
          }
          const destination = type === 'recovery'
            ? `/account/update-password${next === '/' ? '' : `?next=${encodeURIComponent(next)}`}`
            : next
          return NextResponse.redirect(new URL(destination, redirectOrigin))
        }
      }
    } catch {
      // Fall through to the safe, user-facing error state below.
    }
  }

  return NextResponse.redirect(
    new URL('/login?authError=confirmation_failed', redirectOrigin),
  )
}
