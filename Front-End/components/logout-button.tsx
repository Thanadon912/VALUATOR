'use client';

import { useTransition } from 'react';
import { LoaderCircle, LogOut } from 'lucide-react';
import { logout } from '@/app/login/actions';

export function LogoutButton() {
  const [isPending, startTransition] = useTransition();

  return (
    <button
      type="button"
      onClick={() => startTransition(() => logout())}
      disabled={isPending}
      aria-busy={isPending}
      title={isPending ? 'Logging out' : 'Log out'}
      className="workspace-account-action disabled:cursor-wait disabled:opacity-60"
    >
      {isPending ? (
        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      ) : (
        <LogOut className="size-4" aria-hidden="true" />
      )}
      <span className="workspace-account-action__label">
        {isPending ? 'Logging out…' : 'Log out'}
      </span>
    </button>
  );
}
