/**
 * Identitatea vizuala a conturilor OLX si scope-ul selectat.
 *
 * Botul raspunde pe mai multe conturi in acelasi timp, deci fiecare lista din
 * aplicatie amesteca date de pe conturi diferite. Ca sa se distinga dintr-o
 * privire, fiecare cont primeste o culoare stabila (indexul vine de la server,
 * salvat in accounts.json) si o folosim identic in toate modulele.
 */
import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getOlxSession, type OlxAccount } from "@/lib/api";

/** Scope-ul unei pagini: toate conturile sau unul anume. */
export const ALL_ACCOUNTS = "all";
export type AccountScope = typeof ALL_ACCOUNTS | string;

/**
 * Paleta conturilor. Culoarea singura nu e un semnal suficient (daltonism,
 * ecrane proaste), deci apare mereu langa numele contului — e un accent, nu
 * informatia in sine.
 *
 * `dot` coloreaza bulina, `border` bara din stanga randurilor, `chip` eticheta
 * cu numele. Tonurile de dark mode sunt alese sa ramana lizibile pe fundal
 * inchis, nu doar variante mai sterse ale celor de light.
 */
export interface AccountTheme {
  dot: string;
  border: string;
  chip: string;
}

const PALETTE: AccountTheme[] = [
  {
    dot: "bg-sky-500",
    border: "border-l-sky-500",
    chip: "bg-sky-50 text-sky-700 ring-sky-500/20 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-400/25",
  },
  {
    dot: "bg-violet-500",
    border: "border-l-violet-500",
    chip: "bg-violet-50 text-violet-700 ring-violet-500/20 dark:bg-violet-500/15 dark:text-violet-300 dark:ring-violet-400/25",
  },
  {
    dot: "bg-amber-500",
    border: "border-l-amber-500",
    chip: "bg-amber-50 text-amber-800 ring-amber-500/20 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-400/25",
  },
  {
    dot: "bg-teal-500",
    border: "border-l-teal-500",
    chip: "bg-teal-50 text-teal-700 ring-teal-500/20 dark:bg-teal-500/15 dark:text-teal-300 dark:ring-teal-400/25",
  },
  {
    dot: "bg-rose-500",
    border: "border-l-rose-500",
    chip: "bg-rose-50 text-rose-700 ring-rose-500/20 dark:bg-rose-500/15 dark:text-rose-300 dark:ring-rose-400/25",
  },
  {
    dot: "bg-indigo-500",
    border: "border-l-indigo-500",
    chip: "bg-indigo-50 text-indigo-700 ring-indigo-500/20 dark:bg-indigo-500/15 dark:text-indigo-300 dark:ring-indigo-400/25",
  },
  {
    dot: "bg-lime-600",
    border: "border-l-lime-600",
    chip: "bg-lime-50 text-lime-800 ring-lime-600/20 dark:bg-lime-500/15 dark:text-lime-300 dark:ring-lime-400/25",
  },
  {
    dot: "bg-fuchsia-500",
    border: "border-l-fuchsia-500",
    chip: "bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-500/20 dark:bg-fuchsia-500/15 dark:text-fuchsia-300 dark:ring-fuchsia-400/25",
  },
];

/** Culorile contului cu indexul dat (indexul vine de la server). */
export function accountTheme(color: number | undefined): AccountTheme {
  return PALETTE[(color ?? 0) % PALETTE.length];
}

/**
 * Toate conturile din registru — inclusiv cele fara date.
 *
 * Sursa e registrul de conturi, NU datele afisate: altfel un cont fara mesaje
 * ar disparea din filtre si n-ai putea verifica daca e gol sau lipseste.
 */
export function useAccounts() {
  const q = useQuery({ queryKey: ["olxSession"], queryFn: getOlxSession });
  return {
    accounts: q.data?.accounts ?? [],
    isLoading: q.isLoading,
  };
}

/** Contul cu id-ul dat, dintr-o lista de conturi. */
export function findAccount(accounts: OlxAccount[], id: string | undefined) {
  return accounts.find((a) => a.id === id);
}

const SCOPE_STORAGE_KEY = "olxbot.accountScope";

/**
 * Scope-ul selectat, partajat de toate paginile si tinut minte intre sesiuni.
 *
 * Il salvam in localStorage ca sa nu re-selectezi contul la fiecare navigare,
 * si il sincronizam intre taburi/pagini printr-un eveniment: doua componente
 * montate in acelasi timp (selectorul si lista) trebuie sa vada aceeasi valoare.
 */
const SCOPE_EVENT = "olxbot:scope-change";

function readScope(): AccountScope {
  if (typeof window === "undefined") return ALL_ACCOUNTS;
  return window.localStorage.getItem(SCOPE_STORAGE_KEY) || ALL_ACCOUNTS;
}

export function useAccountScope(): [AccountScope, (next: AccountScope) => void] {
  // pornim mereu de la "toate": pe server nu exista localStorage, iar o valoare
  // diferita la prima randare ar produce nepotrivire de hidratare
  const [scope, setScope] = useState<AccountScope>(ALL_ACCOUNTS);

  useEffect(() => {
    setScope(readScope());
    const sync = () => setScope(readScope());
    window.addEventListener(SCOPE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(SCOPE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const update = useCallback((next: AccountScope) => {
    window.localStorage.setItem(SCOPE_STORAGE_KEY, next);
    setScope(next);
    window.dispatchEvent(new Event(SCOPE_EVENT));
  }, []);

  return [scope, update];
}
