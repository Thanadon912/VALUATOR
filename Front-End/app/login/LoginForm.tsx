'use client'

import { useActionState } from 'react'
import Link from 'next/link'
import { login } from './actions'
import { PasswordField } from '@/components/auth/password-field'
import { StatusNotice } from '@/components/ui/status-notice'
import { useAuthFormValidation } from '@/components/auth/use-auth-form-validation'
import { authPageHref } from '@/lib/auth/redirect'
import { type AuthFieldErrors, type AuthFieldValues, validateEmail, validatePassword } from '@/lib/auth/validation'

function validateLogin(values: AuthFieldValues): AuthFieldErrors {
  const email = validateEmail(values.email)
  const password = validatePassword(values.password)
  return {
    ...(email ? { email } : {}),
    ...(password ? { password } : {}),
  }
}

export function LoginForm({ next = '/' }: { next?: string }) {
  const [state, formAction, pending] = useActionState(login, null)

  const validation = useAuthFormValidation(state?.fieldErrors, validateLogin)
  const emailError = validation.errorFor('email')
  const passwordError = validation.errorFor('password')
  const emailProps = validation.fieldProps('email')
  const passwordProps = validation.fieldProps('password')

  return (
    <form action={formAction} noValidate onSubmit={validation.onSubmit} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />
      {state?.error && !emailError && !passwordError && (
        <StatusNotice tone="error" title={state.reason === 'invalid_credentials' ? "We couldn’t sign you in" : "Sign-in is temporarily unavailable"}>
          {state.error}
        </StatusNotice>
      )}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="text-[12px] font-semibold text-[#B8B8C2]">Email</label>
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
          className={`h-[44px] rounded-[10px] bg-[#0B0B0C] px-3 py-2 text-[13px] text-[#FFFFFF] outline-none ring-1 transition-shadow focus:ring-2 focus:ring-[#C6F432] ${emailError ? 'ring-[#FB7185] focus:ring-[#FB7185]' : 'ring-[#242429]'}`}
        />
        {emailError && (
          <p id="email-error" className="text-[13px] leading-5 text-[#FF9C82]">{emailError}</p>
        )}
      </div>

      <PasswordField
        id="password"
        name="password"
        label="Password"
        autoComplete="current-password"
        error={passwordError}
        rightElement={
          <Link href={authPageHref('/forgot-password', next)} className="-mr-1 rounded-sm px-1 py-1 text-[13px] font-medium text-[#C6F432] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C6F432]">
            Forgot password?
          </Link>
        }
        onBlur={passwordProps.onBlur}
        onChange={passwordProps.onChange}
      />

      <button
        type="submit"
        disabled={pending}
        aria-busy={pending}
        className="mt-2 h-[44px] w-full rounded-[10px] bg-[#C6F432] px-3 py-2 text-[13px] font-semibold text-[#0B0B0C] transition-colors hover:bg-[#D4F759] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FFFFFF] focus-visible:ring-offset-2 focus-visible:ring-offset-[#121214] disabled:opacity-50"
      >
        {pending ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}
