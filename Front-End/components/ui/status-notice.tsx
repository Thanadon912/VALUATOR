import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, CircleX, Info } from "lucide-react";

import { cn } from "@/lib/utils";

export type StatusNoticeTone = "success" | "error" | "info" | "caution";

const toneStyles: Record<StatusNoticeTone, { border: string; icon: string; iconNode: ReactNode }> = {
  success: {
    border: "border-[#C6F432]/35",
    icon: "border-[#C6F432]/35 bg-[#C6F432]/10 text-[#C6F432]",
    iconNode: <CircleCheck className="size-4" aria-hidden="true" />,
  },
  error: {
    border: "border-[#6B3A3E]",
    icon: "border-[#6B3A3E] bg-[#FF8E7A]/8 text-[#FF9C82]",
    iconNode: <CircleX className="size-4" aria-hidden="true" />,
  },
  info: {
    border: "border-[#323238]",
    icon: "border-[#323238] bg-white/6 text-[#B8B8C2]",
    iconNode: <Info className="size-4" aria-hidden="true" />,
  },
  caution: {
    border: "border-[#5A4A2D]",
    icon: "border-[#5A4A2D] bg-amber-400/8 text-amber-300",
    iconNode: <CircleAlert className="size-4" aria-hidden="true" />,
  },
};

export function StatusNotice({
  tone,
  title,
  children,
  actions,
  icon,
  className,
  announce = true,
  compact = false,
}: {
  tone: StatusNoticeTone;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  className?: string;
  announce?: boolean;
  compact?: boolean;
}) {
  const styles = toneStyles[tone];
  const liveProps = announce
    ? tone === "error"
      ? { role: "alert" as const, "aria-live": "assertive" as const }
      : { role: "status" as const, "aria-live": "polite" as const }
    : {};

  return (
    <div
      className={cn(
        "rounded-xl border bg-[#0B0B0C] text-[#FFFFFF]",
        styles.border,
        compact ? "px-3 py-2.5" : "p-4",
        className,
      )}
      {...liveProps}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-lg border",
            styles.icon,
          )}
        >
          {icon ?? styles.iconNode}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold leading-5 text-[#FFFFFF]">{title}</p>
          {children ? (
            <div className="mt-1 text-[13px] leading-5 text-[#B8B8C2]">{children}</div>
          ) : null}
          {actions ? <div className="mt-3 flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      </div>
    </div>
  );
}
