'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { after } from 'next/server'

import { authPageHref, safeNextPath } from '@/lib/auth/redirect'
import {
  queueWelcomeEmail,
  requestRecoveryEmail,
  requestSignupEmail,
} from '@/lib/auth/email'
import { getAppBaseUrl } from '@/lib/auth/url'
import { createClient } from '@/lib/supabase/server'
import { isGoogleAuthEnabled } from '@/lib/supabase/config'
import {
  type AuthFieldErrors,
  validateEmail,
  validatePassword,
  validatePasswordConfirmation,
} from '@/lib/auth/validation'

export type AuthReason =
  | 'auth_unavailable'
  | 'confirmation_sent'
  | 'email_test_recipient_only'
  | 'invalid_credentials'
  | 'password_update_failed'
  | 'rate_limited'
  | 'reset_sent'

export type AuthFormState = {
  error?: string
  message?: string
  reason?: AuthReason
  fieldErrors?: AuthFieldErrors
  email?: string
} | null

const AUTH_UNAVAILABLE =
  'Authentication is temporarily unavailable. Please try again later.'

function confirmationPendingState(email: string): AuthFormState {
  return {
    reason: 'confirmation_sent',
    message:
      'If this address can receive a confirmation email, a link will arrive shortly.',
    email,
  }
}

function unavailableState(email?: string): AuthFormState {
  return { reason: 'auth_unavailable', error: AUTH_UNAVAILABLE, email }
}

function readCredentials(formData: FormData) {
  return {
    email: String(formData.get('email') ?? '').trim().toLowerCase(),
    password: String(formData.get('password') ?? ''),
    passwordConfirmation: String(formData.get('passwordConfirmation') ?? ''),
  }
}

export async function login(
  _prevState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const { email, password } = readCredentials(formData)
  const next = safeNextPath(formData.get('next'))

  const emailError = validateEmail(email)
  const passwordError = validatePassword(password)
  if (emailError || passwordError) {
    return {
      error: 'Enter a valid email and password.',
      email,
      fieldErrors: {
        ...(emailError ? { email: emailError } : {}),
        ...(passwordError ? { password: passwordError } : {}),
      },
    }
  }

  let error: { message: string } | null
  let userId: string | undefined
  try {
    const supabase = await createClient()
    const result = await supabase.auth.signInWithPassword({ email, password })
    error = result.error
    userId = result.data.user?.id
  } catch {
    return unavailableState(email)
  }

  if (error) {
    return {
      reason: 'invalid_credentials',
      error: 'Check your email and password, then try again.',
      email,
    }
  }

  if (userId) after(() => queueWelcomeEmail(userId))
  revalidatePath('/', 'layout')
  redirect(next)
}

export async function register(
  _prevState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const { email, password, passwordConfirmation } = readCredentials(formData)
  const next = safeNextPath(formData.get('next'))

  const emailError = validateEmail(email)
  const passwordError = validatePassword(password)
  const confirmationError = validatePasswordConfirmation(password, passwordConfirmation)
  if (emailError || passwordError || confirmationError) {
    return {
      error: 'Please fix the errors below.',
      email,
      fieldErrors: {
        ...(emailError ? { email: emailError } : {}),
        ...(passwordError ? { password: passwordError } : {}),
        ...(confirmationError ? { passwordConfirmation: confirmationError } : {}),
      },
    }
  }

  const result = await requestSignupEmail({ email, password, nextPath: next })
  if (result.status === 'rate_limited') {
    return {
      reason: 'rate_limited',
      error: 'Please wait before requesting another confirmation email.',
      email,
    }
  }
  if (result.status === 'test_recipient_only') {
    return {
      reason: 'email_test_recipient_only',
      error: 'This test environment can send email only to its configured recipient.',
      email,
    }
  }
  if (result.status !== 'accepted') return unavailableState(email)
  return confirmationPendingState(email)
}

export async function signInWithGoogle(
  _prevState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  if (!isGoogleAuthEnabled()) return unavailableState()

  const baseUrl = getAppBaseUrl()
  if (!baseUrl) return unavailableState()

  const next = safeNextPath(formData.get('next'))
  let result
  try {
    const supabase = await createClient()
    result = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${baseUrl}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    })
  } catch {
    return unavailableState()
  }

  if (result.error || !result.data.url) {
    return { reason: 'auth_unavailable', error: 'Google sign-in could not be started. Try again.' }
  }

  redirect(result.data.url)
}

export async function requestPasswordReset(
  _prevState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get('email') ?? '').trim().toLowerCase()
  const next = safeNextPath(formData.get('next'))
  const emailError = validateEmail(email)
  if (emailError) return { error: emailError, fieldErrors: { email: emailError }, email }

  const result = await requestRecoveryEmail({ email, nextPath: next })
  if (result.status === 'rate_limited') {
    return {
      reason: 'rate_limited',
      error: 'Please wait before requesting another reset link for this email.',
      email,
    }
  }
  if (result.status === 'test_recipient_only') {
    return {
      reason: 'email_test_recipient_only',
      error: 'This test environment can send email only to its configured recipient.',
      email,
    }
  }
  if (result.status !== 'accepted') return unavailableState(email)

  return {
    reason: 'reset_sent',
    message:
      'If an account exists for that email, a password reset link is on its way.',
    email,
  }
}

export async function updatePassword(
  _prevState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const password = String(formData.get('password') ?? '')
  const confirmation = String(formData.get('passwordConfirmation') ?? '')
  const next = safeNextPath(formData.get('next'))

  const passwordError = validatePassword(password)
  if (passwordError) {
    return { error: 'Please fix the errors below.', fieldErrors: { password: passwordError } }
  }
  const confirmationError = validatePasswordConfirmation(password, confirmation)
  if (confirmationError) {
    return { error: 'Please fix the errors below.', fieldErrors: { passwordConfirmation: confirmationError } }
  }

  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return { reason: 'password_update_failed', error: 'This reset link has expired. Request a new one.' }

    const { error } = await supabase.auth.updateUser({ password })
    if (error) return { reason: 'password_update_failed', error: 'Your password could not be updated. Request a new reset link and try again.' }
    await supabase.auth.signOut()
  } catch {
    return unavailableState()
  }

  revalidatePath('/', 'layout')
  const loginHref = authPageHref('/login', next)
  redirect(`${loginHref}${loginHref.includes('?') ? '&' : '?'}message=password_updated`)
}

export async function logout() {
  try {
    const supabase = await createClient()
    await supabase.auth.signOut()
  } finally {
    revalidatePath('/', 'layout')
    redirect('/')
  }
}
