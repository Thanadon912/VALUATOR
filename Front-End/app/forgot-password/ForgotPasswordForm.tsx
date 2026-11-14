'use client'

import { useActionState, useState } from 'react'
import { Clock3, Mail } from 'lucide-react'

import { requestPasswordReset } from '@/app/login/actions'
import { StatusNotice } from '@/components/ui/status-notice'
import { useAuthFormValidation } from '@/components/auth/use-auth-form-validation'
import { type AuthFieldErrors, type AuthFieldValues, validateEmail } from '@/lib/auth/validation'

function validateReset(values: AuthFieldValues): AuthFieldErrors {
  const email = validateEmail(values.email)
  return email ? { email } : {}
}

export function ForgotPasswordForm({ next = '/' }: { next?: string }) {
  const [state, formAction, pending] = useActionState(requestPasswordReset, null)
  const [dismissedEmail, setDismissedEmail] = useState<string | null>(null)

  const validation = useAuthFormValidation(state?.fieldErrors, validateReset)
  const emailError = validation.errorFor('email')
  const emailProps = validation.fieldProps('email')
  const showSuccess = state?.reason === 'reset_sent' && dismissedEmail !== state.email

  return (
    <form action={formAction} noValidate onSubmit={validation.onSubmit} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />
      {state?.error && !emailError ? (
        <StatusNotice
          tone={state.reason === 'rate_limited' || state.reason === 'email_test_recipient_only' ? 'caution' : 'error'}
          title={state.reason === 'email_test_recipient_only'
            ? 'Email test mode is active'
            : state.reason === 'rate_limited'
              ? 'A link was requested recently'
              : 'Password reset is temporarily unavailable'}
          icon={state.reason === 'rate_limited' ? <Clock3 className="size-4" aria-hidden="true" /> : undefined}
        >
          {state.reason === 'rate_limited' ? 'Wait a minute, check your inbox, then try again if the email does not arrive.' : state.error}
        </StatusNotice>
      ) : null}
      {showSuccess ? (
        <StatusNotice tone="success" title="Check your inbox" icon={<Mail className="size-4" aria-hidden="true" />}>
          If an account exists for <span className="font-semibold text-[#FFFFFF]">{state.email}</span>, a reset link is on its way. It may take a few minutes to arrive.
        </StatusNotice>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="reset-email" className="text-[12px] font-semibold text-[#B8B8C2]">Email</label>
        <input
          id="reset-email"
          name="email"
          type="email"
          defaultValue={state?.email || ''}
          required
          autoComplete="email"
          aria-invalid={Boolean(emailError)}
          aria-describedby={emailError ? "email-error" : undefined}
          onBlur={emailProps.onBlur}
          onChange={(event) => {
            emailProps.onChange(event)
            if (state?.reason === 'reset_sent') setDismissedEmail(state.email ?? '')
          }}
          className={`h-[44px] rounded-[10px] bg-[#0B0B0C] px-3 py-2 text-[13px] text-[#FFFFFF] outline-none ring-1 transition-shadow focus:ring-2 focus:ring-[#C6F432] disabled:opacity-60 ${emailError ? 'ring-[#FB7185] focus:ring-[#FB7185]' : 'ring-[#242429]'}`}
        />
        {emailError && (
          <p id="email-error" className="text-[13px] leading-5 text-[#FF9C82]">{emailError}</p>
        )}
      </div>
      <button
        type="submit"
        disabled={pending}
        aria-busy={pending}
        className="mt-2 h-[44px] w-full rounded-[10px] bg-[#C6F432] px-3 py-2 text-[13px] font-semibold text-[#0B0B0C] transition-colors hover:bg-[#D4F759] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FFFFFF] focus-visible:ring-offset-2 focus-visible:ring-offset-[#121214] disabled:opacity-50"
      >
        {pending ? 'Sending…' : state?.reason === 'reset_sent' ? 'Send another link' : 'Send reset link'}
      </button>
    </form>
  )
}
