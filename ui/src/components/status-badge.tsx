import { cn } from "@/lib/utils";
import type { ConversationMessage } from "@/lib/types";

const labels: Record<ConversationMessage["status"], string> = {
  sent: "Trimis",
  failed: "Eșuat",
  pending: "În așteptare",
};

const styles: Record<ConversationMessage["status"], string> = {
  sent: "bg-emerald-100 text-emerald-800 ring-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-500/25",
  failed: "bg-red-100 text-red-800 ring-red-200 dark:bg-red-500/15 dark:text-red-300 dark:ring-red-500/25",
  pending: "bg-amber-100 text-amber-800 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/25",
};

export function StatusBadge({ status }: { status: ConversationMessage["status"] }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        styles[status],
      )}
    >
      <span
        className={cn(
          "mr-1.5 h-1.5 w-1.5 rounded-full",
          status === "sent" && "bg-emerald-500",
          status === "failed" && "bg-red-500",
          status === "pending" && "live-dot bg-amber-500",
        )}
      />
      {labels[status]}
    </span>
  );
}