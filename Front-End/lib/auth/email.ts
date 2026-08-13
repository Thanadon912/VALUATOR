import 'server-only'

const API_BASE_URL = process.env.API_BASE_URL ?? 'http://127.0.0.1:8200'

export type AuthEmailResult =
  | { status: 'accepted' }
  | { status: 'rate_limited' }
  | { status: 'test_recipient_only' }
  | { status: 'unavailable' }

async function requestAuthEmail(
  endpoint: 'signup' | 'recovery' | 'welcome',
  payload: Record<string, string>,
): Promise<AuthEmailResult> {
  const token = process.env.EMAIL_INTERNAL_API_TOKEN?.trim()
  if (!token) return { status: 'unavailable' }

  try {
    const response = await fetch(`${API_BASE_URL}/api/internal/auth/email/${endpoint}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      cache: 'no-store',
      signal: AbortSignal.timeout(7_000),
    })
    if (response.status === 202) return { status: 'accepted' }
    if (response.status === 429) return { status: 'rate_limited' }
    if (response.status === 403) {
      const body = await response.json().catch(() => null)
      if (body?.detail?.code === 'email_test_recipient_only') {
        return { status: 'test_recipient_only' }
      }
    }
    return { status: 'unavailable' }
  } catch {
    return { status: 'unavailable' }
  }
}

export function requestSignupEmail(input: {
  email: string
  password: string
  nextPath: string
}) {
  return requestAuthEmail('signup', {
    email: input.email,
    password: input.password,
    next_path: input.nextPath,
  })
}

export function requestRecoveryEmail(input: { email: string; nextPath: string }) {
  return requestAuthEmail('recovery', {
    email: input.email,
    next_path: input.nextPath,
  })
}

export async function queueWelcomeEmail(userId: string): Promise<void> {
  await requestAuthEmail('welcome', { user_id: userId })
}
