import Link from "next/link"
import { cookies } from "next/headers"
import type { User } from "@supabase/supabase-js"
import { createClient } from "@/lib/supabase/server"
import { LogoutButton } from "./logout-button"
import { hasSupabaseConfig } from "@/lib/supabase/config"
import { ArrowLeft, UserRound } from "lucide-react"

const links = [
  { label: "Instrument", href: "/#instrument", mobileHref: "/#instrument" },
  { label: "Methods", href: "/#methods-desktop", mobileHref: "/#methods-mobile" },
  { label: "Sources", href: "/#sources", mobileHref: "/#sources" },
]

export async function Navbar({
  context = "landing",
  returnTo = null,
}: {
  context?: "landing" | "account"
  returnTo?: string | null
}) {
  // Keep the navigation request-rendered so runtime auth environment and
  // session cookies are respected by standalone/Docker deployments.
  await cookies();
  let user: User | null = null;
  if (hasSupabaseConfig()) {
    try {
      const supabase = await createClient();
      user = (await supabase.auth.getUser()).data.user;
    } catch {
      // Authentication must not make the public valuation experience fail
      // when the identity provider is temporarily unavailable.
      user = null;
    }
  }

  return (
    <header className="valuator-nav sticky inset-x-0 top-0 z-50 border-b border-white/10 bg-[#050505]/92 backdrop-blur-md">
      <div className="mx-auto flex min-h-[4.5rem] max-w-[90rem] items-center gap-4 px-5 sm:px-8">
        <Link
          href="/"
          className="valuator-wordmark inline-flex min-h-11 shrink-0 items-center text-xl font-bold text-[#F2F2EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] sm:text-2xl"
          aria-label="VALUATOR home"
        >
          VALUATOR<span aria-hidden="true" className="ml-1 inline-block size-2 bg-[#B7FF3C]" />
        </Link>

        {context === "landing" ? (
          <nav aria-label="Landing page" className="ml-auto hidden items-center gap-6 md:flex">
            {links.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="min-h-11 content-center px-1 text-sm font-medium text-[#A6A69F] transition-colors duration-150 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        ) : null}

        <nav aria-label={context === "account" ? "Account" : "Account actions"} className="ml-auto flex items-center gap-2 sm:gap-3 md:ml-6">
          {context === "account" ? (
            <>
              <Link
                href={returnTo ?? "/#find-fair-value"}
                aria-label={returnTo ? `Back to ${workspaceLabel(returnTo)}` : "New analysis"}
                className="inline-flex min-h-11 items-center rounded-[10px] bg-[#B7FF3C] px-[14px] text-[13px] font-semibold text-[#050505] transition-colors duration-150 hover:bg-[#a6e635] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] focus-visible:ring-offset-2 focus-visible:ring-offset-[#050505]"
              >
                {returnTo ? <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" /> : null}
                <span className="sm:hidden">{returnTo ? "Back" : "New"}</span>
                <span className="hidden sm:inline">{returnTo ? `Back to ${workspaceLabel(returnTo)}` : "New analysis"}</span>
              </Link>
              <Link
                href="/account"
                aria-current="page"
                className="workspace-account-action"
                aria-label="Account"
                title="Account"
              >
                <UserRound className="size-4" aria-hidden="true" />
                <span className="workspace-account-action__label">Account</span>
              </Link>
            </>
          ) : !user ? (
            <>
              <Link
                href="/login"
                className="inline-flex min-h-11 items-center px-1.5 text-[12px] font-medium text-[#C8C8C0] transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] sm:px-3 sm:text-[13px]"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="inline-flex min-h-11 items-center rounded-[10px] bg-[#B7FF3C] px-3 text-[12px] font-semibold text-[#050505] transition-colors duration-150 hover:bg-[#a6e635] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] focus-visible:ring-offset-2 focus-visible:ring-offset-[#050505] sm:px-[14px] sm:text-[13px]"
              >
                Sign up
              </Link>
            </>
          ) : (
            <>
              <Link
                href="/#find-fair-value"
                className="inline-flex min-h-11 items-center rounded-[10px] bg-[#B7FF3C] px-[14px] text-[13px] font-semibold text-[#050505] transition-colors duration-150 hover:bg-[#a6e635] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] focus-visible:ring-offset-2 focus-visible:ring-offset-[#050505]"
              >
                New analysis
              </Link>
              <span className="hidden sm:inline-flex">
                <Link
                  href="/account"
                  className="workspace-account-action"
                  aria-label="Account"
                  title="Account"
                >
                  <UserRound className="size-4" aria-hidden="true" />
                  <span className="workspace-account-action__label">Account</span>
                </Link>
              </span>
              <LogoutButton />
            </>
          )}
        </nav>
      </div>
      {context === "landing" ? (
        <nav aria-label="Landing page mobile" className="flex border-t border-white/10 px-3 md:hidden">
          {links.map((link) => (
            <Link key={link.label} href={link.mobileHref} className="min-h-11 flex-1 content-center text-center text-sm font-medium text-[#C8C8C0] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#B7FF3C]">
              {link.label}
            </Link>
          ))}
        </nav>
      ) : null}
    </header>
  )
}

function workspaceLabel(pathname: string) {
  const match = pathname.match(/^\/stocks\/([^/]+)\/(summary|news|valuation)$/)
  if (!match) return "analysis"
  const section = match[2] === "valuation" ? "valuation" : match[2]
  return `${match[1]} ${section}`
}
