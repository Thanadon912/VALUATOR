import Link from 'next/link'
import type { Metadata } from 'next'
import type { User } from '@supabase/supabase-js'

import { LogoutButton } from '@/components/logout-button'
import { Navbar } from '@/components/navbar'
import { SavedStocksPanel } from '@/features/saved-stocks/saved-stocks-panel'
import { createClient } from '@/lib/supabase/server'
import { hasSupabaseConfig } from '@/lib/supabase/config'
import { safeNextPath } from '@/lib/auth/redirect'

export const dynamic = 'force-dynamic'
export const metadata: Metadata = {
  title: 'Account — VALUATOR',
  description: 'Resume saved stock research and review your VALUATOR account details.',
}

function providerLabel(provider: unknown): string {
  if (provider === 'google') return 'Google'
  if (provider === 'email') return 'Email and password'
  if (typeof provider !== 'string' || !provider.trim()) return 'Unavailable'
  return provider
    .trim()
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function isMissingSession(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const candidate = error as { name?: unknown; status?: unknown; code?: unknown }
  return candidate.status === 401
    || candidate.name === 'AuthSessionMissingError'
    || candidate.code === 'session_not_found'
}

export default async function AccountPage({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string }>
}) {
  const requestedReturnTo = (await searchParams).returnTo
  const safeReturnTo = requestedReturnTo ? safeNextPath(requestedReturnTo) : null
  const returnTo = safeReturnTo && safeReturnTo !== '/' && safeReturnTo !== '/account'
    ? safeReturnTo
    : null
  let user: User | null = null
  let authUnavailable = false
  if (hasSupabaseConfig()) {
    try {
      const supabase = await createClient()
      const result = await supabase.auth.getUser()
      if (result.error && !isMissingSession(result.error)) authUnavailable = true
      user = result.data.user
    } catch {
      authUnavailable = true
    }
  }

  const heading = user ? 'Your Valuator account' : authUnavailable ? 'Your saved research' : 'Saved stocks on this device'
  const description = user
    ? 'Resume saved analyses, review current market context, and keep your account details close at hand.'
    : authUnavailable
      ? 'Saved stocks on this device remain available while account verification is temporarily unavailable.'
      : 'Review saved stocks on this device or sign in to sync them privately across devices.'

  return (
    <div className="valuator-site min-h-screen overflow-x-clip bg-[#050505] text-[#F2F2EE]">
      <Navbar context="account" returnTo={returnTo} />
      <main className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
        <header className="mb-7">
          <h1 className="text-2xl font-bold tracking-tight text-[#EFFAF4]">{heading}</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-6 text-[#90B09E]">{description}</p>
        </header>

        <div id="account-saved-stocks"><SavedStocksPanel variant="account" /></div>

        <section aria-labelledby="account-details-heading" className="mt-7 rounded-[12px] border border-[#1E293B] bg-[#0B0F17]/90 p-5">
          <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
            {authUnavailable ? <div role="status" aria-live="polite">
              <h2 id="account-details-heading" className="text-[14px] font-semibold text-[#EFFAF4]">Account details unavailable</h2>
              <p className="mt-2 max-w-xl text-[13px] leading-6 text-[#90B09E]">We could not verify your account right now. Saved stocks on this device remain available.</p>
            </div> : user ? <div>
              <h2 id="account-details-heading" className="text-[14px] font-semibold text-[#EFFAF4]">Account details</h2>
              <dl className="mt-3 grid gap-2 text-[13px] sm:grid-cols-[7rem_1fr]">
                <dt className="text-[#6F8B7B]">Email</dt>
                <dd className="break-all text-[#DCEBE2]">{user.email ?? 'Unavailable'}</dd>
                <dt className="text-[#6F8B7B]">Signed in with</dt>
                <dd className="text-[#DCEBE2]">{providerLabel(user.app_metadata.provider)}</dd>
              </dl>
            </div> : <div>
              <h2 id="account-details-heading" className="text-[14px] font-semibold text-[#EFFAF4]">Account details</h2>
              <p className="mt-2 max-w-xl text-[13px] leading-6 text-[#90B09E]">Your stocks are stored only in this browser. Sign in or create an account to merge them into a private, cross-device list.</p>
            </div>}
            {authUnavailable ? (
              <Link href="/account" className="inline-flex min-h-11 items-center rounded-[10px] border border-[#2A3B31] px-4 text-sm font-semibold text-[#EFFAF4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">Try again</Link>
            ) : user ? <LogoutButton /> : (
              <div className="flex flex-wrap gap-2">
                <Link href="/login?next=%2Faccount" className="inline-flex min-h-11 items-center rounded-[10px] border border-[#2A3B31] px-4 text-sm font-semibold text-[#EFFAF4] transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">Sign in</Link>
                <Link href="/register?next=%2Faccount" className="inline-flex min-h-11 items-center rounded-[10px] bg-[#B7FF3C] px-4 text-sm font-semibold text-[#050505] transition-colors hover:bg-[#a6e635] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] focus-visible:ring-offset-2 focus-visible:ring-offset-[#050505]">Create account</Link>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}
