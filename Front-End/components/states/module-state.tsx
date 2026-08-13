import type { SummaryModule } from "@/lib/api/types";

export function ModuleState({
  module,
  compact = false,
}: {
  module: SummaryModule;
  compact?: boolean;
}) {
  const tone =
    module.status === "success"
      ? "bg-[#B7FF3C]/80"
      : module.status === "partial" || module.status === "stale"
        ? "bg-amber-400/80"
        : "bg-rose-400/80";

  return (
    <div
      role="status"
      aria-label={`${module.status.replaceAll("_", " ")}: ${module.message}`}
      className={
        compact
          ? "mt-3 inline-flex max-w-full items-start gap-1.5 font-mono text-[13px] leading-5 text-[#90B09E]"
          : "mt-4 flex max-w-full items-center gap-2 rounded-lg border border-white/10 bg-[#0B0F17]/45 px-3 py-2 font-mono text-[13px] text-[#90B09E]"
      }
    >
      <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${tone}`} aria-hidden="true" />
      <p className="min-w-0 break-words">{module.message}</p>
    </div>
  );
}
