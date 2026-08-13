import { AuthPageShell } from "@/components/auth/auth-page-shell";
import { safeNextPath } from "@/lib/auth/redirect";
import { isGoogleAuthEnabled } from "@/lib/supabase/config";
import { RegisterForm } from "./RegisterForm";

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const next = safeNextPath((await searchParams).next);

  return (
    <AuthPageShell
      title="Create your account"
      description="Save stocks privately across devices and pick up where you left off."
      contextAction="register"
      nextPath={next}
    >
      <RegisterForm next={next} googleEnabled={isGoogleAuthEnabled()} />

      <p className="mt-6 text-center text-[12px] text-[#90B09E]">
        Saved stocks are private to your account.
      </p>
    </AuthPageShell>
  );
}
