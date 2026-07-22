import { useQuery } from "@tanstack/react-query";

import { getOlxSession, type OlxAccount } from "@/lib/api";

/** Numele afisat al unui cont: numele/emailul OLX detectat la login,
 *  altfel eticheta locala ("Cont 1"). */
export function accountDisplayName(a: Pick<OlxAccount, "label" | "username" | "name">) {
  return a.name ?? a.username ?? a.label;
}

export function useOlxSession() {
  return useQuery({
    queryKey: ["olxSession"],
    queryFn: getOlxSession,
    // in timpul login-ului manual, urmarim cand se conecteaza contul
    refetchInterval: (q) => (q.state.data?.login_running ? 2500 : 15000),
  });
}
