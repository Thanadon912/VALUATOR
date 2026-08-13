import { AuthPageShell } from "@/components/auth/auth-page-shell";
import { GoogleAuthButton } from "@/components/auth/google-auth-button";
import { authPageHref, safeNextPath } from "@/lib/auth/redirect";
import { isGoogleAuthEnabled } from "@/lib/supabase/config";
import { LoginForm } from "./LoginForm";
import Link from "next/link";
import { StatusNotice } from "@/components/ui/status-notice";

const AUTH_MESSAGES: Record<string, string> = {
  confirmation_failed: "It may have expired or already been used. Choose a recovery option below.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; authError?: string; message?: string }>;
}) {
  const params = await searchParams;
  const next = safeNextPath(params.next);
  const authError = params.authError ? AUTH_MESSAGES[params.authError] : null;
  const passwordUpdated = params.message === "password_updated";
  const notice = authError ? (
    <StatusNotice
      tone="error"
      title="This link is no longer valid"
      actions={(
        <>
          <Link className="inline-flex min-h-11 items-center font-semibold text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]" href={authPageHref("/forgot-password", next)}>
            Request a reset link
          </Link>
          <Link className="inline-flex min-h-11 items-center font-semibold text-[#DCEBE2] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]" href={authPageHref("/register", next)}>
            Return to account setup
          </Link>
        </>
      )}
    >
      {authError}
    </StatusNotice>
  ) : passwordUpdated ? (
    <StatusNotice tone="success" title="Password updated">
      Sign in with your new password.
    </StatusNotice>
  ) : null;

  return (
    <AuthPageShell
      title="Sign in"
      description="Return to your saved stocks and valuation workspace."
      contextAction="login"
      nextPath={next}
      notice={notice}
    >
      <LoginForm next={next} />
      {isGoogleAuthEnabled() ? <GoogleAuthButton next={next} /> : null}

      <p className="mt-6 text-center text-[12px] text-[#90B09E]">
        Saved stocks are private to your account.
      </p>
    </AuthPageShell>
  );
}
