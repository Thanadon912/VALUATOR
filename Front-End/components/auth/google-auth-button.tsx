'use client'

import { useActionState } from 'react'

import { signInWithGoogle } from '@/app/login/actions'
import { StatusNotice } from '@/components/ui/status-notice'

export function GoogleAuthButton({ next = '/' }: { next?: string }) {
  const [state, formAction, pending] = useActionState(signInWithGoogle, null)

  return (
    <form action={formAction} className="mt-4">
      <input type="hidden" name="next" value={next} />
      <div className="mb-4 flex items-center gap-3 text-[12px] text-[#8E8E99]" aria-hidden="true">
        <span className="h-px flex-1 bg-[#242429]" />
        or continue with
        <span className="h-px flex-1 bg-[#242429]" />
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
        className="inline-flex h-[44px] w-full items-center justify-center rounded-[10px] border border-[#323238] bg-[#0B0B0C] px-3 text-[13px] font-semibold text-[#FFFFFF] transition-colors hover:border-[#FFFFFF]/40 hover:bg-[#18181B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C6F432] disabled:opacity-50"
      >
        {pending ? 'Connecting to Google…' : 'Continue with Google'}
      </button>
    </form>
  )
}
