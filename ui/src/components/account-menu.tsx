import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, LogOut, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { useState, type ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  activateOlxAccount,
  addOlxAccount,
  getOlxSession,
  signOutOlxAccount,
  type OlxAccount,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** Numele afisat al unui cont: numele/emailul OLX detectat la login,
 *  altfel eticheta locala ("Cont 1"). */
export function accountDisplayName(
  a: Pick<OlxAccount, "label" | "username" | "name">,
) {
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

/**
 * Meniul de conturi OLX (switch / adauga / sign out), refolosit in sidebar
 * (butonul "OLX Bot") si in cardul de stare de pe dashboard. `children` e
 * trigger-ul pe care se da click.
 */
export function AccountMenu({
  children,
  align = "start",
}: {
  children: ReactNode;
  align?: "start" | "end";
}) {
  const qc = useQueryClient();
  const sessionQ = useOlxSession();
  const session = sessionQ.data;
  const loginRunning = session?.login_running ?? false;

  // datele (produse, conversatii, setari, statistici) sunt per cont, deci
  // la schimbarea contului reincarcam tot, nu doar sesiunea si statusul
  const invalidate = () => {
    qc.invalidateQueries();
  };

  const switchAccount = useMutation({
    mutationFn: activateOlxAccount,
    onSuccess: ({ bot_stopped }) => {
      invalidate();
      toast.success(
        bot_stopped
          ? "Cont schimbat — botul a fost oprit, repornește-l pe noul cont"
          : "Cont schimbat",
      );
    },
    onError: () => toast.error("Nu am putut schimba contul"),
  });

  const addAccount = useMutation({
    mutationFn: () => addOlxAccount(),
    onSuccess: () => {
      invalidate();
      toast.info("S-a deschis fereastra de login pentru noul cont.");
    },
    onError: () => toast.error("Nu am putut adăuga contul"),
  });

  // contul pentru care e deschis dialogul de stergere definitiva
  const [purgeTarget, setPurgeTarget] = useState<OlxAccount | null>(null);

  const signOut = useMutation({
    mutationFn: (id: string) => signOutOlxAccount(id),
    onSuccess: () => {
      invalidate();
      toast.success(
        "Cont deconectat — produsele, conversațiile și setările rămân salvate",
      );
    },
    onError: () => toast.error("Nu am putut deconecta contul"),
  });

  const purgeAccount = useMutation({
    mutationFn: (id: string) => signOutOlxAccount(id, true),
    onSuccess: () => {
      invalidate();
      setPurgeTarget(null);
      toast.success("Cont șters definitiv, cu toate datele lui");
    },
    onError: () => toast.error("Nu am putut șterge contul"),
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="w-64">
        <DropdownMenuLabel>Conturi OLX</DropdownMenuLabel>
        {(session?.accounts ?? []).length === 0 ? (
          <div className="px-2 py-1.5 text-xs text-muted-foreground">
            Niciun cont — adaugă unul mai jos.
          </div>
        ) : null}
        {(session?.accounts ?? []).map((a) => (
          <DropdownMenuItem
            key={a.id}
            disabled={a.active || switchAccount.isPending}
            onSelect={() => switchAccount.mutate(a.id)}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 shrink-0 rounded-full",
                a.connected ? "bg-emerald-500" : "bg-red-500",
              )}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate">{accountDisplayName(a)}</span>
              <span className="block truncate text-[10px] text-muted-foreground">
                {a.username ? a.username + " · " : ""}
                {a.connected ? "conectat" : "neconectat"}
              </span>
            </span>
            {a.active ? (
              <Check className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
            ) : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={addAccount.isPending || loginRunning}
          onSelect={() => addAccount.mutate()}
        >
          <UserPlus className="h-3.5 w-3.5" strokeWidth={1.5} />
          {loginRunning ? "Login în curs…" : "Adaugă cont nou"}
        </DropdownMenuItem>
        {session?.account?.connected ? (
          <DropdownMenuItem
            disabled={signOut.isPending}
            onSelect={() => signOut.mutate(session.account!.id)}
          >
            <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
            <span>
              <span className="block">Deconectează contul activ</span>
              <span className="block text-[10px] text-muted-foreground">
                datele rămân salvate
              </span>
            </span>
          </DropdownMenuItem>
        ) : null}
        {session?.account ? (
          <DropdownMenuItem
            disabled={purgeAccount.isPending}
            onSelect={() => setPurgeTarget(session.account)}
            className="text-red-600 focus:text-red-600 dark:text-red-400 dark:focus:text-red-400"
          >
            <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
            Șterge contul activ și datele
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>

      <AlertDialog
        open={purgeTarget !== null}
        onOpenChange={(open) => {
          if (!open) setPurgeTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Ștergi definitiv contul{" "}
              {purgeTarget ? accountDisplayName(purgeTarget) : ""}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Se pierd toate datele acestui cont: produsele (cu întrebările
              frecvente), istoricul conversațiilor, setările și sesiunea de
              login. Acțiunea nu poate fi anulată. Dacă vrei doar să te
              deloghezi, folosește „Deconectează contul activ" — datele
              rămân salvate.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Renunță</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 text-white hover:bg-red-700"
              disabled={purgeAccount.isPending}
              onClick={() => purgeTarget && purgeAccount.mutate(purgeTarget.id)}
            >
              Șterge tot
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DropdownMenu>
  );
}
