import Link from "next/link";
import { ReactNode } from "react";
import { authPageHref } from "@/lib/auth/redirect";

type AuthPageShellProps = {
  children: ReactNode;
  title: string;
  description: string;
  contextAction: "login" | "register" | "forgot-password" | "update-password";
  nextPath?: string;
  notice?: ReactNode;
};

function destinationLabel(nextPath: string): string | null {
  if (nextPath === "/account") return "your account";
  const match = nextPath.match(/^\/stocks\/([^/]+)\/(summary|news|valuation)$/);
  if (!match) return null;
  return `${match[1]} ${match[2]}`;
}

export function AuthPageShell({
  children,
  title,
  description,
  contextAction,
  nextPath = "/",
  notice,
}: AuthPageShellProps) {
  const destination = destinationLabel(nextPath);
  let actionLabel = "";
  let actionHref = "";
  
  if (contextAction === "login") {
    actionLabel = "Create account";
    actionHref = authPageHref("/register", nextPath);
  } else if (contextAction === "register" || contextAction === "forgot-password") {
    actionLabel = "Sign in";
    actionHref = authPageHref("/login", nextPath);
  } else if (contextAction === "update-password") {
    actionLabel = "Cancel";
    actionHref = authPageHref("/login", nextPath);
  }

  return (
    <div className="valuator-site min-h-[100svh] bg-[#050505] text-[#F2F2EE] flex flex-col overflow-x-clip">
      <header className="flex h-16 shrink-0 items-center justify-between px-5 sm:px-8 bg-[#050505]">
        <Link
          href="/"
          className="valuator-wordmark inline-flex items-center text-xl font-bold text-[#F2F2EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] sm:text-2xl"
          aria-label="VALUATOR home"
        >
          VALUATOR<span aria-hidden="true" className="ml-1 inline-block size-2 bg-[#B7FF3C]" />
        </Link>
        <Link
          href={actionHref}
          className="inline-flex min-h-[44px] items-center px-1 text-[13px] font-medium text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
        >
          {actionLabel}
        </Link>
      </header>
      <main className="flex flex-1 justify-center px-4 pb-6 pt-8 sm:px-6 sm:pb-16 sm:pt-20">
        <div className="h-fit w-full max-w-[448px] rounded-[14px] border border-[#24372C] bg-[#0B0F0D] p-5 sm:p-6">
          <div className="mb-6 text-center">
            <h1 className="text-[18px] font-bold tracking-tight text-[#EFFAF4]">{title}</h1>
            <p className="mt-1 text-[13px] leading-5 text-[#90B09E]">{description}</p>
            {destination ? (
              <p className="mt-2 text-[13px] font-medium text-[#C6D8CD]">
                Continue to {destination} after sign-in.
              </p>
            ) : null}
          </div>

          {notice ? <div className="mb-5">{notice}</div> : null}

          {children}
        </div>
      </main>
    </div>
  );
}
