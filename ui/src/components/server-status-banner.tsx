import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { getHealth } from "@/lib/api";

/**
 * Banner discret afisat cand server.py nu raspunde. Fara el, un server
 * nepornit ar produce doar erori tacute in fiecare pagina.
 */
export function ServerStatusBanner() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5000,
    retry: false,
  });

  // isError = fetch a esuat (server oprit / inaccesibil)
  if (!health.isError) return null;

  return (
    <div className="sticky top-0 z-40 border-b border-amber-300/60 bg-amber-50 text-amber-900 dark:border-amber-400/25 dark:bg-amber-500/10 dark:text-amber-200">
      <div className="mx-auto flex max-w-7xl items-center gap-2.5 px-4 py-2.5 text-sm md:px-10">
        <AlertTriangle className="h-4 w-4 shrink-0 animate-pulse" strokeWidth={1.5} />
        <span className="min-w-0">
          Serverul botului nu răspunde. Pornește-l în terminal:{" "}
          <code className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[12px] dark:bg-amber-500/15">
            .venv\Scripts\python.exe server.py
          </code>
        </span>
      </div>
    </div>
  );
}
