import { redirect } from 'next/navigation'

import { AuthPageShell } from '@/components/auth/auth-page-shell'
import { createClient } from '@/lib/supabase/server'
import { hasSupabaseConfig } from '@/lib/supabase/config'
import { UpdatePasswordForm } from './UpdatePasswordForm'
import { safeNextPath } from '@/lib/auth/redirect'

export const dynamic = 'force-dynamic'

export default async function UpdatePasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const next = safeNextPath((await searchParams).next)
  if (!hasSupabaseConfig()) redirect('/login?authError=confirmation_failed')

  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login?authError=confirmation_failed')

  return (
    <AuthPageShell
      title="Choose a new password"
      description="Your reset session is ready."
      contextAction="update-password"
      nextPath={next}
    >
      <UpdatePasswordForm next={next} />
    </AuthPageShell>
  )
}
