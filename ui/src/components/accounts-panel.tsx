/**
 * Panoul de administrare a conturilor OLX.
 *
 * Inlocuieste vechiul meniu care lucra pe "contul activ": acum fiecare cont
 * din lista are actiunile lui (login, deconectare, stergere), iar alegerea
 * contului pe care lucrezi se face din comutatorul din bara laterala.
 *
 * Arata pentru fiecare cont ce conteaza cand ruleaza mai multi boti deodata:
 * culoarea, daca sesiunea OLX e valida si daca botul lui merge acum.
 */
import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Globe, KeyRound, Loader2, LogOut, RotateCw, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";

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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { accountDisplayName, useOlxSession } from "@/components/account-menu";
import { AccountDot } from "@/components/account-scope";
import {
  addOlxAccount,
  getBotStatus,
  getDockerAccounts,
  getDockerStatus,
  restartAccountDocker,
  setAccountProxy,
  signOutOlxAccount,
  startAccountDocker,
  startOlxLoginForAccount,
  stopAccountDocker,
  type OlxAccount,
} from "@/lib/api";
import { useAccountScope } from "@/lib/accounts";
import { cn } from "@/lib/utils";

/**
 * Panoul de conturi. `children` e declansatorul (logo-ul din bara laterala,
 * butonul "Gestionează" din dashboard).
 */
export function AccountsPanel({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [purgeTarget, setPurgeTarget] = useState<OlxAccount | null>(null);
  const [proxyTarget, setProxyTarget] = useState<OlxAccount | null>(null);
  const [proxyForm, setProxyForm] = useState({ server: "", username: "", password: "" });
  const [, setScope] = useAccountScope();

  const session = useOlxSession().data;
  const accounts = session?.accounts ?? [];
  const loginRunning = session?.login_running ?? false;

  // starea botilor: un cont care ruleaza nu poate fi deconectat fara ca
  // serverul sa opreasca intai botul, deci o aratam explicit
  const botStatus = useQuery({
    queryKey: ["botStatus"],
    queryFn: () => getBotStatus(),
    refetchInterval: open ? 4000 : false,
  });
  const runningIds = new Set(
    (botStatus.data?.accounts ?? []).filter((a) => a.running).map((a) => a.account_id),
  );

  // starea Docker: disponibilitatea daemonului + starea/jobul fiecarui cont.
  // Poll rapid cat timp panoul e deschis, ca progresul build-ului (poate
  // dura minute) sa se vada live, nu doar la refresh manual.
  const dockerStatus = useQuery({
    queryKey: ["dockerStatus"],
    queryFn: getDockerStatus,
    refetchInterval: open ? 5000 : false,
  });
  const dockerAccounts = useQuery({
    queryKey: ["dockerAccounts"],
    queryFn: getDockerAccounts,
    refetchInterval: open ? 2500 : false,
  });
  const dockerByAccount = new Map((dockerAccounts.data ?? []).map((d) => [d.account_id, d]));

  const startDocker = useMutation({
    mutationFn: (id: string) => startAccountDocker(id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["dockerAccounts"] });
      toast.info(
        data.already_running
          ? "O operație Docker e deja în curs pentru acest cont."
          : "Pornesc containerul — poate dura câteva minute la prima rulare.",
      );
    },
    onError: () => toast.error("Nu am putut porni containerul"),
  });

  const stopDocker = useMutation({
    mutationFn: (id: string) => stopAccountDocker(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dockerAccounts"] });
      toast.info("Opresc containerul...");
    },
    onError: () => toast.error("Nu am putut opri containerul"),
  });

  const restartDocker = useMutation({
    mutationFn: (id: string) => restartAccountDocker(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dockerAccounts"] });
      toast.info("Repornesc containerul — setările noi se aplică după ce pornește din nou.");
    },
    onError: () => toast.error("Nu am putut reporni containerul"),
  });

  // datele afisate peste tot depind de conturi, deci reincarcam tot
  const invalidate = () => qc.invalidateQueries();

  const addAccount = useMutation({
    mutationFn: () => addOlxAccount(),
    onSuccess: () => {
      invalidate();
      toast.info("S-a deschis fereastra de login pentru noul cont.");
    },
    onError: () => toast.error("Nu am putut adăuga contul"),
  });

  // login pentru contul din rand, nu pentru "contul activ"
  const login = useMutation({
    mutationFn: (id: string) => startOlxLoginForAccount(id),
    onSuccess: () => {
      invalidate();
      toast.info("S-a deschis o fereastră de browser — loghează-te în contul OLX.");
    },
    onError: () => toast.error("Nu am putut deschide fereastra de login"),
  });

  const signOut = useMutation({
    mutationFn: (id: string) => signOutOlxAccount(id),
    onSuccess: () => {
      invalidate();
      toast.success("Cont deconectat — produsele, conversațiile și setările rămân salvate");
    },
    onError: () => toast.error("Nu am putut deconecta contul"),
  });

  // proxy de iesire per cont — conturi diferite pe acelasi IP sunt usor de
  // corelat de sistemele anti-frauda OLX; fiecare cont poate iesi separat
  const saveProxy = useMutation({
    mutationFn: (vars: { id: string; server: string; username: string; password: string }) =>
      setAccountProxy(vars.id, {
        server: vars.server,
        username: vars.username,
        password: vars.password,
      }),
    onSuccess: (data) => {
      invalidate();
      setProxyTarget(null);
      const restartNote =
        data.restarted === "thread"
          ? " — botul s-a repornit automat, se aplică deja"
          : data.restarted === "docker"
            ? " — containerul se repornește automat, se aplică imediat ce pornește"
            : " — se aplică la următoarea pornire a botului pe acest cont";
      toast.success((data.has_proxy ? "Proxy salvat" : "Proxy șters") + restartNote);
    },
    onError: () => toast.error("Nu am putut salva proxy-ul"),
  });

  const purge = useMutation({
    mutationFn: (id: string) => signOutOlxAccount(id, true),
    onSuccess: (_data, id) => {
      // scope-ul putea fi chiar pe contul sters — il ducem inapoi pe "toate"
      setScope("all");
      invalidate();
      setPurgeTarget(null);
      toast.success("Cont șters definitiv, cu toate datele lui");
      void id;
    },
    onError: () => toast.error("Nu am putut șterge contul"),
  });

  return (
    <>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>{children}</DialogTrigger>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Conturi OLX</DialogTitle>
            <DialogDescription>
              Fiecare cont are sesiunea, produsele și setările lui. Contul pe care lucrezi se alege
              din comutatorul „Cont" din bara laterală.
            </DialogDescription>
          </DialogHeader>

          {dockerStatus.data && !dockerStatus.data.available ? (
            <p className="rounded-lg bg-muted/50 px-3 py-2 text-[11px] text-muted-foreground">
              Docker indisponibil{dockerStatus.data.detail ? `: ${dockerStatus.data.detail}` : ""}
              {" — "}pornirea în container e dezactivată până repornești Docker Desktop.
            </p>
          ) : null}

          {accounts.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              Niciun cont încă. Adaugă primul cont mai jos.
            </p>
          ) : (
            <ul className="space-y-2">
              {accounts.map((a) => {
                const running = runningIds.has(a.id);
                const docker = dockerByAccount.get(a.id);
                const dockerJob = docker?.job && !docker.job.done ? docker.job : null;
                const dockerError = docker?.job?.done ? docker.job.error : null;
                return (
                  <li
                    key={a.id}
                    className="flex items-center gap-3 rounded-xl border border-border/70 bg-muted/30 p-3"
                  >
                    <AccountDot color={a.color} className="h-2.5 w-2.5" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{accountDisplayName(a)}</div>
                      <div className="truncate text-[11px] text-muted-foreground">
                        {a.username ?? "fără email detectat"}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <StateChip
                          ok={a.connected}
                          label={a.connected ? "conectat" : "neconectat"}
                        />
                        {a.connected ? (
                          <StateChip ok={running} label={running ? "bot pornit" : "bot oprit"} />
                        ) : null}
                        {docker?.container_running ? (
                          <StateChip ok label="container Docker" />
                        ) : null}
                      </div>
                      {dockerJob ? (
                        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                          <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.5} />
                          {dockerJob.step}
                        </div>
                      ) : null}
                      {dockerError ? (
                        <div
                          className="mt-1 truncate text-[11px] text-red-600 dark:text-red-400"
                          title={docker?.job?.log_tail || undefined}
                        >
                          Docker: {dockerError}
                        </div>
                      ) : null}
                    </div>

                    <div className="flex shrink-0 flex-col gap-1">
                      {a.connected ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 justify-start px-2 text-xs"
                          disabled={signOut.isPending}
                          onClick={() => signOut.mutate(a.id)}
                          title="Șterge doar sesiunea; datele rămân"
                        >
                          <LogOut className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                          Deconectează
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 justify-start px-2 text-xs"
                          disabled={login.isPending || loginRunning}
                          onClick={() => login.mutate(a.id)}
                        >
                          <KeyRound className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                          {loginRunning ? "Login în curs…" : "Conectează"}
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 justify-start px-2 text-xs"
                        onClick={() => {
                          setProxyForm({
                            server: a.proxy_server ?? "",
                            username: a.proxy_username ?? "",
                            password: "",
                          });
                          setProxyTarget(a);
                        }}
                        title="Proxy de ieșire — cont diferit, IP diferit"
                      >
                        <Globe className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                        {a.has_proxy ? "Proxy" : "Fără proxy"}
                      </Button>
                      {dockerStatus.data?.available && a.connected ? (
                        docker?.container_running ? (
                          <div className="flex gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 flex-1 justify-start px-2 text-xs"
                              disabled={!!dockerJob || stopDocker.isPending}
                              onClick={() => stopDocker.mutate(a.id)}
                            >
                              <Box className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                              Oprește Docker
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 shrink-0"
                              disabled={!!dockerJob || restartDocker.isPending}
                              onClick={() => restartDocker.mutate(a.id)}
                              title="Repornește containerul — necesar ca setările noi (ex. modelul LLM) să se aplice"
                            >
                              <RotateCw className="h-3.5 w-3.5" strokeWidth={1.5} />
                            </Button>
                          </div>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 justify-start px-2 text-xs"
                            disabled={!!dockerJob || startDocker.isPending}
                            onClick={() => startDocker.mutate(a.id)}
                            title="Rulează botul acestui cont într-un container Docker separat"
                          >
                            <Box className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                            Pornește în Docker
                          </Button>
                        )
                      ) : null}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 justify-start px-2 text-xs text-red-600 hover:text-red-700 dark:text-red-400"
                        onClick={() => setPurgeTarget(a)}
                      >
                        <Trash2 className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.5} />
                        Șterge
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <DialogFooter className="sm:justify-start">
            <Button
              variant="outline"
              disabled={addAccount.isPending || loginRunning}
              onClick={() => addAccount.mutate()}
            >
              {addAccount.isPending || loginRunning ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.5} />
              ) : (
                <UserPlus className="mr-2 h-4 w-4" strokeWidth={1.5} />
              )}
              {loginRunning ? "Login în curs…" : "Adaugă cont nou"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={proxyTarget !== null} onOpenChange={(o) => !o && setProxyTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              Proxy — {proxyTarget ? accountDisplayName(proxyTarget) : ""}
            </DialogTitle>
            <DialogDescription>
              Contul iese pe internet prin acest proxy/VPN în loc de IP-ul mașinii. Util când ai mai
              multe conturi OLX pe același calculator — IP diferit per cont, mai greu de corelat.
              Lasă adresa goală ca să ștergi proxy-ul. Dacă botul acestui cont rulează deja, se
              repornește automat ca să preia noul proxy — nu trebuie să faci nimic în plus.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="proxy-server">Adresă (server:port)</Label>
              <Input
                id="proxy-server"
                placeholder="http://host:port sau socks5://host:port"
                value={proxyForm.server}
                onChange={(e) => setProxyForm((f) => ({ ...f, server: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="proxy-username">Utilizator (opțional)</Label>
                <Input
                  id="proxy-username"
                  value={proxyForm.username}
                  onChange={(e) => setProxyForm((f) => ({ ...f, username: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="proxy-password">Parolă (opțional)</Label>
                <Input
                  id="proxy-password"
                  type="password"
                  placeholder={proxyTarget?.has_proxy ? "neschimbată dacă o lași goală" : ""}
                  value={proxyForm.password}
                  onChange={(e) => setProxyForm((f) => ({ ...f, password: e.target.value }))}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setProxyTarget(null)}>
              Renunță
            </Button>
            <Button
              disabled={saveProxy.isPending}
              onClick={() =>
                proxyTarget &&
                saveProxy.mutate({
                  id: proxyTarget.id,
                  server: proxyForm.server.trim(),
                  username: proxyForm.username.trim(),
                  password: proxyForm.password.trim(),
                })
              }
            >
              {saveProxy.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.5} />
              ) : null}
              Salvează
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={purgeTarget !== null} onOpenChange={(o) => !o && setPurgeTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Ștergi definitiv contul {purgeTarget ? accountDisplayName(purgeTarget) : ""}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Se pierd toate datele acestui cont: produsele (cu întrebările frecvente), istoricul
              conversațiilor, setările și sesiunea de login. Botul lui se oprește. Acțiunea nu poate
              fi anulată. Dacă vrei doar să te deloghezi, folosește „Deconectează" — datele rămân
              salvate.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Renunță</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 text-white hover:bg-red-700"
              disabled={purge.isPending}
              onClick={() => purgeTarget && purge.mutate(purgeTarget.id)}
            >
              Șterge tot
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/** Pastila de stare: verde pentru bine, gri pentru inactiv. */
function StateChip({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cn(
        "rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset",
        ok
          ? "bg-emerald-50 text-emerald-700 ring-emerald-500/20 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-400/25"
          : "bg-muted text-muted-foreground ring-border",
      )}
    >
      {label}
    </span>
  );
}
