import { AuthPageShell } from "@/components/auth/auth-page-shell";
import { ForgotPasswordForm } from "./ForgotPasswordForm";
import { safeNextPath } from "@/lib/auth/redirect";

// The recovery flow uses cookie-backed Supabase server actions. Keep this
// route dynamic so production builds never cache it as a static page and then
// fail when the request needs cookies.
export const dynamic = "force-dynamic";

export default async function ForgotPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const next = safeNextPath((await searchParams).next);
  return (
    <AuthPageShell
      title="Reset password"
      description="We'll email you a secure link to choose a new password."
      contextAction="forgot-password"
      nextPath={next}
    >
      <ForgotPasswordForm next={next} />
    </AuthPageShell>
  );
}
