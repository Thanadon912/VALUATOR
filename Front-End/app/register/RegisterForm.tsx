'use client'

import { useActionState, useState } from 'react'
import Link from 'next/link'
import { Mail } from 'lucide-react'
import { register } from '../login/actions'
import { PasswordField } from '@/components/auth/password-field'
import { GoogleAuthButton } from '@/components/auth/google-auth-button'
import { StatusNotice } from '@/components/ui/status-notice'
import { useAuthFormValidation } from '@/components/auth/use-auth-form-validation'
import { authPageHref } from '@/lib/auth/redirect'
import {
  type AuthFieldErrors,
  type AuthFieldValues,
  validateEmail,
  validatePassword,
  validatePasswordConfirmation,
} from '@/lib/auth/validation'

function validateRegistration(values: AuthFieldValues): AuthFieldErrors {
  const email = validateEmail(values.email)
  const password = validatePassword(values.password)
  const passwordConfirmation = validatePasswordConfirmation(values.password, values.passwordConfirmation)
  return {
    ...(email ? { email } : {}),
    ...(password ? { password } : {}),
    ...(passwordConfirmation ? { passwordConfirmation } : {}),
  }
}

export function RegisterForm({ next = '/', googleEnabled = false }: { next?: string; googleEnabled?: boolean }) {
  const [state, formAction, pending] = useActionState(register, null)
  const [editingEmail, setEditingEmail] = useState<string | null>(null)

  const validation = useAuthFormValidation(state?.fieldErrors, validateRegistration)
  const emailError = validation.errorFor('email')
  const passwordError = validation.errorFor('password')
  const confirmationError = validation.errorFor('passwordConfirmation')
  const emailProps = validation.fieldProps('email')
  const passwordProps = validation.fieldProps('password')
  const confirmationProps = validation.fieldProps('passwordConfirmation')

  if (state?.reason === 'confirmation_sent' && editingEmail !== state.email) {
    return (
      <StatusNotice
        tone="success"
        title="Check your inbox"
        icon={<Mail className="size-4" aria-hidden="true" />}
        actions={(
          <>
            <button
              type="button"
              onClick={() => setEditingEmail(state.email ?? '')}
              className="inline-flex min-h-11 items-center font-semibold text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            >
              Use a different email
            </button>
            <Link
              href={authPageHref('/login', next)}
              className="inline-flex min-h-11 items-center font-semibold text-[#DCEBE2] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            >
              Sign in
            </Link>
            <Link
              href={authPageHref('/forgot-password', next)}
              className="inline-flex min-h-11 items-center font-semibold text-[#DCEBE2] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            >
              Reset password
            </Link>
          </>
        )}
      >
        If <span className="font-semibold text-[#DCEBE2]">{state.email}</span> can receive a confirmation email, a link will arrive shortly. Already registered? Sign in or reset your password. Saved stocks on this device remain available.
      </StatusNotice>
    )
  }

  return (
    <>
    <form action={formAction} noValidate onSubmit={validation.onSubmit} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />
      {state?.error && !emailError && !passwordError && !confirmationError ? (
        <StatusNotice
          tone={state.reason === 'rate_limited' || state.reason === 'email_test_recipient_only' ? 'caution' : 'error'}
          title={state.reason === 'email_test_recipient_only'
            ? 'Email test mode is active'
            : state.reason === 'rate_limited'
              ? 'A confirmation was requested recently'
              : 'Account creation is temporarily unavailable'}
        >
          {state.error}
        </StatusNotice>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="text-[12px] font-semibold text-[#90B09E]">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          defaultValue={state?.email || ''}
          required
          autoComplete="email"
          aria-invalid={Boolean(emailError)}
          aria-describedby={emailError ? "email-error" : undefined}
          onBlur={emailProps.onBlur}
          onChange={emailProps.onChange}
          className={`h-[44px] rounded-[10px] bg-[#0B0F17] px-3 py-2 text-[13px] text-[#EFFAF4] outline-none ring-1 transition-shadow focus:ring-2 focus:ring-[#B7FF3C] ${emailError ? 'ring-[#FB7185] focus:ring-[#FB7185]' : 'ring-[#1E293B]'}`}
        />
        {emailError && (
          <p id="email-error" className="text-[13px] leading-5 text-[#FF9C82]">{emailError}</p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <PasswordField
          id="password"
          name="password"
          label="Password"
          autoComplete="new-password"
          error={passwordError}
          describedBy="password-requirements"
          onBlur={passwordProps.onBlur}
          onChange={passwordProps.onChange}
        />
        <p id="password-requirements" className="text-[13px] leading-5 text-[#7F998A]">Use at least 8 characters.</p>
      </div>

      <div className="flex flex-col gap-1.5">
        <PasswordField
          id="passwordConfirmation"
          name="passwordConfirmation"
          label="Confirm Password"
          autoComplete="new-password"
          error={confirmationError}
          onBlur={confirmationProps.onBlur}
          onChange={confirmationProps.onChange}
        />
      </div>

      <button
        type="submit"
        disabled={pending}
        aria-busy={pending}
        className="mt-2 h-[44px] w-full rounded-[10px] bg-[#B7FF3C] px-3 py-2 text-[13px] font-semibold text-[#010303] transition-colors hover:bg-[#a6e635] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#EFFAF4] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F0D] disabled:opacity-50"
      >
        {pending ? 'Creating account…' : 'Create account'}
      </button>
    </form>
    {googleEnabled ? <GoogleAuthButton next={next} /> : null}
    </>
  )
}
