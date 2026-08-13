'use client'

import { useActionState } from 'react'
import Link from 'next/link'

import { updatePassword } from '@/app/login/actions'
import { PasswordField } from '@/components/auth/password-field'
import { StatusNotice } from '@/components/ui/status-notice'
import { useAuthFormValidation } from '@/components/auth/use-auth-form-validation'
import { authPageHref } from '@/lib/auth/redirect'
import {
  type AuthFieldErrors,
  type AuthFieldValues,
  validatePassword,
  validatePasswordConfirmation,
} from '@/lib/auth/validation'

function validateNewPassword(values: AuthFieldValues): AuthFieldErrors {
  const password = validatePassword(values.password)
  const passwordConfirmation = validatePasswordConfirmation(values.password, values.passwordConfirmation)
  return {
    ...(password ? { password } : {}),
    ...(passwordConfirmation ? { passwordConfirmation } : {}),
  }
}

export function UpdatePasswordForm({ next = '/' }: { next?: string }) {
  const [state, formAction, pending] = useActionState(updatePassword, null)

  const validation = useAuthFormValidation(state?.fieldErrors, validateNewPassword)
  const passwordError = validation.errorFor('password')
  const confirmationError = validation.errorFor('passwordConfirmation')
  const passwordProps = validation.fieldProps('password')
  const confirmationProps = validation.fieldProps('passwordConfirmation')

  return (
    <form action={formAction} noValidate onSubmit={validation.onSubmit} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />
      {state?.error && !passwordError && !confirmationError ? (
        <StatusNotice
          tone="error"
          title={state.reason === 'password_update_failed' ? 'Your reset session needs attention' : 'Password update is temporarily unavailable'}
          actions={state.reason === 'password_update_failed' ? (
            <Link
              href={authPageHref('/forgot-password', next)}
              className="inline-flex min-h-11 items-center font-semibold text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            >
              Request a new reset link
            </Link>
          ) : undefined}
        >
          {state.error}
        </StatusNotice>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <PasswordField
          id="new-password"
          name="password"
          label="New password"
          autoComplete="new-password"
          error={passwordError}
          describedBy="new-password-requirements"
          onBlur={passwordProps.onBlur}
          onChange={passwordProps.onChange}
        />
        <p id="new-password-requirements" className="text-[13px] leading-5 text-[#7F998A]">Use at least 8 characters.</p>
      </div>

      <PasswordField
        id="password-confirmation"
        name="passwordConfirmation"
        label="Confirm new password"
        autoComplete="new-password"
        error={confirmationError}
        onBlur={confirmationProps.onBlur}
        onChange={confirmationProps.onChange}
      />

      <button
        type="submit"
        disabled={pending}
        aria-busy={pending}
        className="mt-2 h-[44px] w-full rounded-[10px] bg-[#B7FF3C] px-3 py-2 text-[13px] font-semibold text-[#010303] transition-colors hover:bg-[#a6e635] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#EFFAF4] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F0D] disabled:opacity-50"
      >
        {pending ? 'Updating…' : 'Update password'}
      </button>
    </form>
  )
}
