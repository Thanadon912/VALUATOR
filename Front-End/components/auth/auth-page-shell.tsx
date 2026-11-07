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
    <div className="valuator-site min-h-[100svh] bg-[#0B0B0C] text-[#FFFFFF] flex flex-col overflow-x-clip">
      <header className="flex h-16 shrink-0 items-center justify-between px-5 sm:px-8 bg-[#0B0B0C]">
        <Link
          href="/"
          className="valuator-wordmark inline-flex items-center text-xl font-bold text-[#FFFFFF] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C6F432] sm:text-2xl"
          aria-label="VALUATOR home"
        >
          VALUATOR<span aria-hidden="true" className="ml-1 inline-block size-2 bg-[#C6F432]" />
        </Link>
        <Link
          href={actionHref}
          className="inline-flex min-h-[44px] items-center px-1 text-[13px] font-medium text-[#C6F432] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C6F432]"
        >
          {actionLabel}
        </Link>
      </header>
      <main className="flex flex-1 justify-center px-4 pb-6 pt-8 sm:px-6 sm:pb-16 sm:pt-20">
        <div className="h-fit w-full max-w-[448px] rounded-[14px] border border-[#242429] bg-[#121214] p-5 sm:p-6">
          <div className="mb-6 text-center">
            <h1 className="text-[18px] font-bold tracking-tight text-[#FFFFFF]">{title}</h1>
            <p className="mt-1 text-[13px] leading-5 text-[#B8B8C2]">{description}</p>
            {destination ? (
              <p className="mt-2 text-[13px] font-medium text-[#FFFFFF]">
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
