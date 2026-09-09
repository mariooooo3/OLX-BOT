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
import {
  Box,
  Globe,
  KeyRound,
  Loader2,
  LogOut,
  Plus,
  RotateCw,
  ShieldCheck,
  Trash2,
  UserPlus,
  Wifi,
} from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { accountDisplayName, useOlxSession } from "@/components/account-menu";
import { AccountDot } from "@/components/account-scope";
import {
  addOlxAccount,
  createProxy,
  deleteProxy,
  getBotStatus,
  getDockerAccounts,
  getDockerStatus,
  getProxies,
  restartAccountDocker,
  setAccountProxy,
  signOutOlxAccount,
  startAccountDocker,
  startOlxLoginForAccount,
  stopAccountDocker,
  testProxy,
  testProxyFull,
  type OlxAccount,
  type ProxyInput,
} from "@/lib/api";
import type { Proxy, ProxyFullTestResult, ProxyTestResult } from "@/lib/types";
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
  // doar id-ul, nu obiectul cont — altfel dupa o asignare de proxy reusita,
  // proxyTarget ar ramane un instantaneu vechi (proxy_id stale) in loc sa
  // reflecte imediat noua asignare din raspunsul invalidat de React Query
  const [proxyTargetId, setProxyTargetId] = useState<string | null>(null);
  const [newProxyOpen, setNewProxyOpen] = useState(false);
  const [newProxyForm, setNewProxyForm] = useState({
    label: "",
    server: "",
    username: "",
    password: "",
    skipValidation: false,
  });
  const [, setScope] = useAccountScope();

  const session = useOlxSession().data;
  const accounts = session?.accounts ?? [];
  const loginRunning = session?.login_running ?? false;
  // derivat din `accounts` la fiecare randare — reflecta imediat proxy_id-ul
  // proaspat dupa o asignare, spre deosebire de un obiect cont stocat direct
  const proxyTarget = accounts.find((a) => a.id === proxyTargetId) ?? null;

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

  // registrul central de proxy-uri — un singur loc de adevar, ca acelasi
  // proxy sa nu ajunga din greseala pe doua conturi (vezi core/proxies.py)
  const proxiesQ = useQuery({
    queryKey: ["proxies"],
    queryFn: getProxies,
    refetchInterval: proxyTarget ? 4000 : false,
  });

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
  // corelat de sistemele anti-frauda OLX; fiecare cont poate iesi separat,
  // printr-un proxy din registrul central (asignare prin id, nu adresa direct)
  const assignProxy = useMutation({
    mutationFn: (vars: { accountId: string; proxyId: string | null }) =>
      setAccountProxy(vars.accountId, vars.proxyId),
    onSuccess: (data) => {
      invalidate();
      const restartNote =
        data.restarted === "thread"
          ? " — botul s-a repornit automat, se aplică deja"
          : data.restarted === "docker"
            ? " — containerul se repornește automat, se aplică imediat ce pornește"
            : "";
      if (data.moved_from) {
        toast.info(
          `Proxy mutat aici — contul „${data.moved_from.account_label}” a rămas fără proxy.`,
        );
      } else {
        toast.success((data.has_proxy ? "Proxy asignat" : "Proxy dezasignat") + restartNote);
      }
    },
    onError: () => toast.error("Nu am putut schimba proxy-ul contului"),
  });

  // adauga un proxy nou in registru SI il asigneaza imediat contului deschis
  // in dialog — fluxul cel mai comun (rar adaugi un proxy fara sa-l folosesti)
  const createAndAssignProxy = useMutation({
    mutationFn: (vars: { accountId: string; input: ProxyInput }) => createProxy(vars.input),
    onSuccess: (data, vars) => {
      qc.invalidateQueries({ queryKey: ["proxies"] });
      assignProxy.mutate({ accountId: vars.accountId, proxyId: data.proxy.id });
      setNewProxyOpen(false);
      setNewProxyForm({ label: "", server: "", username: "", password: "", skipValidation: false });
      announceProxyTest(data.test, "Proxy adăugat");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Nu am putut adăuga proxy-ul"),
  });

  const testProxyMutation = useMutation({
    mutationFn: (id: string) => testProxy(id),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["proxies"] });
      announceProxyTest(result, "Proxy testat");
    },
    onError: () => toast.error("Nu am putut testa proxy-ul"),
  });

  // verificare completa, cu Chromium real — mai lenta, dar prinde
  // discrepante intre testul rapid (`requests`) si browserul real
  const testProxyFullMutation = useMutation({
    mutationFn: (id: string) => testProxyFull(id),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["proxies"] });
      announceProxyFullTest(result);
    },
    onError: () => toast.error("Nu am putut rula verificarea completă"),
  });

  const deleteProxyMutation = useMutation({
    mutationFn: (id: string) => deleteProxy(id, true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["proxies"] });
      toast.success("Proxy șters din registru");
    },
    onError: () => toast.error("Nu am putut șterge proxy-ul"),
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
                        onClick={() => setProxyTargetId(a.id)}
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

      <Dialog
        open={proxyTarget !== null}
        onOpenChange={(o) => {
          if (!o) {
            setProxyTargetId(null);
            setNewProxyOpen(false);
            setNewProxyForm({
              label: "",
              server: "",
              username: "",
              password: "",
              skipValidation: false,
            });
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Proxy — {proxyTarget ? accountDisplayName(proxyTarget) : ""}</DialogTitle>
            <DialogDescription>
              Contul iese pe internet prin proxy-ul ales, în loc de IP-ul mașinii. Fiecare proxy
              există o singură dată în registru — dacă alegi unul folosit deja de alt cont, acela
              rămâne fără proxy (repornit automat dacă rula). Dacă botul acestui cont rulează deja,
              se repornește automat ca să preia schimbarea.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <button
              type="button"
              disabled={assignProxy.isPending}
              onClick={() =>
                proxyTarget && assignProxy.mutate({ accountId: proxyTarget.id, proxyId: null })
              }
              className={cn(
                "w-full rounded-lg border px-2.5 py-2 text-left text-xs transition-colors",
                proxyTarget && !proxyTarget.proxy_id
                  ? "border-primary/50 bg-primary/5"
                  : "border-border/70 bg-muted/30 hover:bg-muted/50",
              )}
            >
              Fără proxy (iese pe IP-ul mașinii)
            </button>

            {proxiesQ.isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <ul className="max-h-56 space-y-1.5 overflow-y-auto">
                {(proxiesQ.data ?? []).map((p) => (
                  <ProxyRow
                    key={p.id}
                    proxy={p}
                    selected={proxyTarget?.proxy_id === p.id}
                    onSelect={() =>
                      proxyTarget &&
                      assignProxy.mutate({ accountId: proxyTarget.id, proxyId: p.id })
                    }
                    onTest={() => testProxyMutation.mutate(p.id)}
                    onTestFull={() => testProxyFullMutation.mutate(p.id)}
                    onDelete={() => {
                      const msg = p.account_id
                        ? `Ștergi proxy-ul „${p.label}”? E folosit acum de contul „${p.account_label}” — va rămâne fără proxy.`
                        : `Ștergi proxy-ul „${p.label}” din registru?`;
                      if (window.confirm(msg)) deleteProxyMutation.mutate(p.id);
                    }}
                    disabled={assignProxy.isPending}
                    testing={testProxyMutation.isPending && testProxyMutation.variables === p.id}
                    testingFull={
                      testProxyFullMutation.isPending && testProxyFullMutation.variables === p.id
                    }
                  />
                ))}
                {(proxiesQ.data ?? []).length === 0 ? (
                  <p className="px-1 py-2 text-xs text-muted-foreground">
                    Niciun proxy în registru încă.
                  </p>
                ) : null}
              </ul>
            )}

            {newProxyOpen ? (
              <div className="space-y-2 rounded-lg border border-dashed border-border/80 p-2.5">
                <Input
                  placeholder="Etichetă (opțional, ex. „Vultr București”)"
                  value={newProxyForm.label}
                  onChange={(e) => setNewProxyForm((f) => ({ ...f, label: e.target.value }))}
                />
                <Input
                  placeholder="socks5://host:port sau http://host:port"
                  value={newProxyForm.server}
                  onChange={(e) => setNewProxyForm((f) => ({ ...f, server: e.target.value }))}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="Utilizator (opțional)"
                    value={newProxyForm.username}
                    onChange={(e) => setNewProxyForm((f) => ({ ...f, username: e.target.value }))}
                  />
                  <Input
                    type="password"
                    placeholder="Parolă (opțional)"
                    value={newProxyForm.password}
                    onChange={(e) => setNewProxyForm((f) => ({ ...f, password: e.target.value }))}
                  />
                </div>
                {createAndAssignProxy.isError ? (
                  <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={newProxyForm.skipValidation}
                      onChange={(e) =>
                        setNewProxyForm((f) => ({ ...f, skipValidation: e.target.checked }))
                      }
                    />
                    Salvează chiar dacă testul de conectivitate eșuează
                  </label>
                ) : null}
                <div className="flex justify-end gap-2 pt-0.5">
                  <Button variant="ghost" size="sm" onClick={() => setNewProxyOpen(false)}>
                    Renunță
                  </Button>
                  <Button
                    size="sm"
                    disabled={!newProxyForm.server.trim() || createAndAssignProxy.isPending}
                    onClick={() =>
                      proxyTarget &&
                      createAndAssignProxy.mutate({
                        accountId: proxyTarget.id,
                        input: {
                          label: newProxyForm.label.trim(),
                          server: newProxyForm.server.trim(),
                          username: newProxyForm.username.trim(),
                          password: newProxyForm.password.trim(),
                          skip_validation: newProxyForm.skipValidation,
                        },
                      })
                    }
                  >
                    {createAndAssignProxy.isPending ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                    ) : null}
                    Testează și salvează
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="w-full gap-1.5"
                onClick={() => setNewProxyOpen(true)}
              >
                <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
                Adaugă proxy nou
              </Button>
            )}
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setProxyTargetId(null)}>
              Închide
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

/**
 * Un proxy din registru, in dialogul de asignare per cont — arata starea
 * ultimului test si, daca e folosit de alt cont, un avertisment (selectarea
 * lui il muta aici si il lasa fara proxy pe celalalt).
 */
function ProxyRow({
  proxy,
  selected,
  disabled,
  testing,
  testingFull,
  onSelect,
  onTest,
  onTestFull,
  onDelete,
}: {
  proxy: Proxy;
  selected: boolean;
  disabled: boolean;
  testing: boolean;
  testingFull: boolean;
  onSelect: () => void;
  onTest: () => void;
  onTestFull: () => void;
  onDelete: () => void;
}) {
  const usedByOther = proxy.account_id !== null && !selected;
  return (
    <li>
      <div
        className={cn(
          "flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors",
          selected ? "border-primary/50 bg-primary/5" : "border-border/70 bg-muted/30",
        )}
      >
        <button
          type="button"
          disabled={disabled}
          onClick={onSelect}
          className="min-w-0 flex-1 text-left"
        >
          <div className="flex items-center gap-1.5">
            <ProxyStatusDot check={proxy.last_check} />
            <span className="truncate font-medium">{proxy.label}</span>
          </div>
          <div className="truncate text-[11px] text-muted-foreground">{proxy.server}</div>
          {proxy.last_full_check ? (
            <div
              className={cn(
                "mt-0.5 truncate text-[10px]",
                proxy.last_full_check.ok
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400",
              )}
            >
              verificare completă: {proxy.last_full_check.ok ? "ok" : "eșuată"}
              {proxy.last_full_check.browser_ok === false ? " (browser real)" : ""}
            </div>
          ) : null}
          {usedByOther ? (
            <div className="mt-0.5 truncate text-[10px] text-amber-600 dark:text-amber-400">
              folosit de {proxy.account_label}
            </div>
          ) : null}
        </button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          disabled={testing}
          onClick={onTest}
          title="Testează conectivitatea către OLX (rapid)"
        >
          {testing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
          ) : (
            <Wifi className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0"
          disabled={testingFull}
          onClick={onTestFull}
          title="Testează complet, cu browser real (mai lent, ~5-15s)"
        >
          {testingFull ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
          ) : (
            <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 text-red-600 hover:text-red-700 dark:text-red-400"
          onClick={onDelete}
          title="Șterge din registru"
        >
          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
        </Button>
      </div>
    </li>
  );
}

/**
 * Bulina de stare a ultimului test: verde ok, chihlimbar ok-dar-țară-greșită
 * (funcțional, dar iese din altă țară decât România — vezi core/proxies.py),
 * roșu eșuat, gri netestat.
 */
function ProxyStatusDot({ check }: { check: Proxy["last_check"] }) {
  if (!check) {
    return <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300" title="Netestat" />;
  }
  if (!check.ok) {
    return (
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full bg-red-500"
        title={check.error ?? "Eșuat"}
      />
    );
  }
  if (check.country_mismatch) {
    return (
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500"
        title={`Funcțional, dar iese din ${check.country} — nu România (${check.latency_ms} ms)`}
      />
    );
  }
  return (
    <span
      className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"
      title={`OK, România (${check.latency_ms} ms)`}
    />
  );
}

/** Toast-ul rezultatului unui test — succes curat, avertisment (funcțional
 *  dar din altă țară) sau eroare, ca userul să nu afle abia după ce
 *  asignează proxy-ul pe un cont că iese din altă țară decât România. */
function announceProxyTest(result: ProxyTestResult | null, prefix: string): void {
  if (!result) {
    toast.success(`${prefix} (netestat)`);
    return;
  }
  if (!result.ok) {
    toast.error(result.error ?? "Proxy nefuncțional");
    return;
  }
  if (result.country_mismatch) {
    toast.warning(
      `${prefix} — funcțional, dar iese din ${result.country}, nu România ` +
        `(${result.latency_ms} ms). Risc de corelare pentru un cont OLX.ro.`,
    );
    return;
  }
  toast.success(`${prefix} — funcțional, România (${result.latency_ms} ms)`);
}

/**
 * Toast-ul verificării complete (Chromium real). Distinge explicit cazul
 * "testul rapid a trecut, dar browserul real nu" — exact discrepanța care a
 * invalidat o sesiune OLX reală în timpul testării acestei funcționalități.
 */
function announceProxyFullTest(result: ProxyFullTestResult): void {
  if (!result.ok) {
    if (result.browser_ok === false) {
      toast.error(
        `Verificare completă eșuată — testul rapid a trecut, dar browserul ` +
          `real nu a putut folosi acest proxy: ${result.browser_error}`,
      );
    } else {
      toast.error(result.error ?? "Proxy nefuncțional");
    }
    return;
  }
  if (result.country_mismatch) {
    toast.warning(
      `Verificare completă OK, dar proxy-ul iese din ${result.country}, nu ` +
        `România (browser real: ${result.browser_latency_ms} ms). Risc de corelare.`,
    );
    return;
  }
  toast.success(`Verificare completă OK — browser real, România (${result.browser_latency_ms} ms)`);
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
