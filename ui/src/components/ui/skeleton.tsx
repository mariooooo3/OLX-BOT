import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("shimmer rounded-lg bg-foreground/[0.05]", className)}
      {...props}
    />
  );
}

export { Skeleton };
