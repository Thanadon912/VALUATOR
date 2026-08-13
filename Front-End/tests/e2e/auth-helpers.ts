import type { Page } from '@playwright/test'

export async function confirmSignup(
  page: Page,
  email: string,
  nextPath = '/',
): Promise<void> {
  const params = new URLSearchParams({
    token_hash: `signup:${email.toLowerCase()}`,
    type: 'signup',
    next: nextPath,
  })
  await page.goto(`/auth/confirm?${params.toString()}`)
}

export async function openPasswordRecovery(
  page: Page,
  email: string,
  nextPath = '/',
): Promise<void> {
  const params = new URLSearchParams({
    token_hash: `recovery:${email.toLowerCase()}`,
    type: 'recovery',
    next: nextPath,
  })
  await page.goto(`/auth/confirm?${params.toString()}`)
}
