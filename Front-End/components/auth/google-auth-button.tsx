'use client'

import { useActionState } from 'react'

import { signInWithGoogle } from '@/app/login/actions'
import { StatusNotice } from '@/components/ui/status-notice'

export function GoogleAuthButton({ next = '/' }: { next?: string }) {
  const [state, formAction, pending] = useActionState(signInWithGoogle, null)

  return (
    <form action={formAction} className="mt-4">
      <input type="hidden" name="next" value={next} />
      <div className="mb-4 flex items-center gap-3 text-[12px] text-[#90B09E]" aria-hidden="true">
        <span className="h-px flex-1 bg-[#1E293B]" />
        or continue with
        <span className="h-px flex-1 bg-[#1E293B]" />
      </div>
      {state?.error ? (
        <StatusNotice className="mb-3" tone="error" title="Google sign-in is temporarily unavailable" compact>
          {state.error}
        </StatusNotice>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        aria-busy={pending}
        className="inline-flex h-[44px] w-full items-center justify-center rounded-[10px] border border-[#2A3B31] bg-[#090D0B] px-3 text-[13px] font-semibold text-[#EFFAF4] transition-colors hover:border-[#486153] hover:bg-[#101713] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] disabled:opacity-50"
      >
        {pending ? 'Connecting to Google…' : 'Continue with Google'}
      </button>
    </form>
  )
}
