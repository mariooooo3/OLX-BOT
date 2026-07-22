/**
 * Componentele comune pentru lucrul cu mai multe conturi: selectorul de scope,
 * eticheta colorata a unui cont si starea goala per cont.
 *
 * Sunt folosite identic in Dashboard / Conversatii / Produse / Setari, ca
 * "contul Trep" sa arate la fel peste tot.
 */
import { useEffect } from "react";
import { Check, ChevronDown, Users } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  ALL_ACCOUNTS,
  accountTheme,
  useAccountScope,
  useAccounts,
  type AccountScope,
} from "@/lib/accounts";
import { accountDisplayName } from "@/components/account-menu";
import { activateOlxAccount, type OlxAccount } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Bulina colorata a unui cont. */
export function AccountDot({
  color,
  className,
}: {
  color: number | undefined;
  className?: string;
}) {
  return (
    <span className={cn("h-2 w-2 shrink-0 rounded-full", accountTheme(color).dot, className)} />
  );
}

/**
 * Eticheta unui cont: bulina colorata + nume. Culoarea e accentul, numele e
 * informatia — asa ramane clar si pentru cine nu distinge culorile.
 */
export function AccountBadge({
  account,
  className,
}: {
  account: { display_name?: string; label?: string; color?: number } | undefined;
  className?: string;
}) {
  if (!account) return null;
  const name = account.display_name ?? account.label ?? "Cont";
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full px-2 py-0.5",
        "text-[11px] font-medium ring-1 ring-inset",
        accountTheme(account.color).chip,
        className,
      )}
    >
      <AccountDot color={account.color} className="h-1.5 w-1.5" />
      <span className="truncate">{name}</span>
    </span>
  );
}

/**
 * Comutatorul principal de cont — controlul cel mai vizibil din aplicatie.
 *
 * E unul singur, in bara laterala, si se aplica peste tot: dashboard, produse,
 * conversatii, setari. Arata mereu pe ce lucrezi ("Toate conturile" sau un cont
 * anume), cu culoarea contului ca accent.
 *
 * Cand alegi un singur cont, il facem si contul "activ" pe server: altfel
 * actiunile care au nevoie de o tinta implicita (produs nou) ar putea nimeri
 * alt cont decat cel pe care il vezi.
 */
export function AccountScopeSwitcher({ compact = false }: { compact?: boolean }) {
  const [scope, setScope] = useAccountScope();
  const { accounts, isLoading } = useAccounts();
  const qc = useQueryClient();

  const selected = accounts.find((a) => a.id === scope);
  const isAll = scope === ALL_ACCOUNTS || !selected;

  // Scope-ul e tinut in localStorage, deci poate ramane pe un cont sters intre
  // timp. Fara resetare, toate paginile ar cere date pentru un cont inexistent
  // si ar primi 404.
  useEffect(() => {
    if (isLoading || scope === ALL_ACCOUNTS) return;
    if (!accounts.some((a) => a.id === scope)) setScope(ALL_ACCOUNTS);
  }, [accounts, isLoading, scope, setScope]);

  const activate = useMutation({
    mutationFn: activateOlxAccount,
    // datele afisate depind de scope; le reimprospatam dupa schimbare
    onSettled: () => qc.invalidateQueries(),
  });

  const choose = (next: AccountScope) => {
    setScope(next);
    if (next !== ALL_ACCOUNTS) activate.mutate(next);
    else qc.invalidateQueries();
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "group flex w-full items-center gap-2.5 rounded-xl border px-3 text-left",
            "border-border/80 bg-card shadow-[inset_0_1px_0_oklch(1_0_0/0.6)]",
            "transition-colors duration-300 hover:bg-muted/60",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            compact ? "py-1.5" : "py-2.5",
          )}
        >
          {isAll ? (
            // mai multe bulinte suprapuse = "toate conturile", fara sa
            // privilegiem culoarea vreunui cont anume
            <span className="flex shrink-0 -space-x-1">
              {accounts.slice(0, 3).map((a) => (
                <span
                  key={a.id}
                  className={cn(
                    "h-2.5 w-2.5 rounded-full ring-2 ring-card",
                    accountTheme(a.color).dot,
                  )}
                />
              ))}
              {accounts.length === 0 ? (
                <Users className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} />
              ) : null}
            </span>
          ) : (
            <span
              className={cn("h-2.5 w-2.5 shrink-0 rounded-full", accountTheme(selected?.color).dot)}
            />
          )}
          <span className="min-w-0 flex-1">
            <span className="block text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Cont
            </span>
            <span className="block truncate text-sm font-semibold leading-tight">
              {isAll
                ? `Toate conturile${accounts.length ? ` (${accounts.length})` : ""}`
                : accountDisplayName(selected!)}
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-300 group-data-[state=open]:rotate-180"
            strokeWidth={1.5}
          />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>
          <span className="block">Pe ce cont lucrezi</span>
          <span className="block text-[10px] font-normal text-muted-foreground">
            se aplică în tot dashboard-ul
          </span>
        </DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => choose(ALL_ACCOUNTS)}>
          <span className="flex shrink-0 -space-x-1">
            {accounts.slice(0, 3).map((a) => (
              <span
                key={a.id}
                className={cn(
                  "h-2 w-2 rounded-full ring-2 ring-popover",
                  accountTheme(a.color).dot,
                )}
              />
            ))}
          </span>
          <span className="min-w-0 flex-1">Toate conturile</span>
          <SelectedCheck selected={isAll} />
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {accounts.map((a) => (
          <DropdownMenuItem key={a.id} onSelect={() => choose(a.id)}>
            <AccountDot color={a.color} />
            <span className="min-w-0 flex-1">
              <span className="block truncate">{accountDisplayName(a)}</span>
              <span className="block truncate text-[10px] text-muted-foreground">
                {a.connected ? "conectat" : "neconectat"}
              </span>
            </span>
            <SelectedCheck selected={scope === a.id} />
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * Textul care descrie scope-ul curent — folosit in starile goale, ca sa fie
 * clar ca lista e goala PENTRU CONTUL ALES, nu ca aplicatia n-are date.
 */
export function scopeLabel(scope: AccountScope, accounts: OlxAccount[]): string | null {
  if (scope === ALL_ACCOUNTS) return null;
  const account = accounts.find((a) => a.id === scope);
  return account ? accountDisplayName(account) : null;
}

/** Bara colorata din stanga unui rand/card, pe culoarea contului. */
export function accountBorderClass(color: number | undefined) {
  return cn("border-l-[3px]", accountTheme(color).border);
}

/** Marcaj pentru optiunea selectata in liste custom (meniuri de conturi). */
export function SelectedCheck({ selected }: { selected: boolean }) {
  return selected ? (
    <Check className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
  ) : (
    <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-0" strokeWidth={1.5} />
  );
}
