import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  MessagesSquare,
  AlertTriangle,
  Package,
  Clock,
  Power,
  PowerOff,
  KeyRound,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Trash2,
  ArrowUpRight,
} from "lucide-react";
import { toast } from "sonner";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import { AccountMenu, accountDisplayName, useOlxSession } from "@/components/account-menu";
import {
  clearBotErrors,
  getBotErrors,
  getBotStatus,
  getConversations,
  getMessagesPerDay,
  getProducts,
  startBot,
  startOlxLogin,
  stopBot,
} from "@/lib/api";
import { timeAgo, truncate, formatDateTime, formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  component: DashboardPage,
});

function DashboardPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [errorsOpen, setErrorsOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState<"messages" | "products" | "poll" | null>(null);
  const lastAutoOpenedError = useRef<string | null>(null);
  const statusQ = useQuery({
    queryKey: ["botStatus"],
    queryFn: getBotStatus,
    // starea botului se schimba pe server (porniri esuate, erori in bucla),
    // asa ca o reimprospatam periodic; in timpul opririi, mai des, ca sa
    // prindem repede momentul in care botul chiar s-a oprit
    refetchInterval: (q) => (q.state.data?.stopping ? 1500 : 5000),
  });
  const productsQ = useQuery({ queryKey: ["products"], queryFn: getProducts });
  const convosQ = useQuery({ queryKey: ["conversations"], queryFn: getConversations });
  const chartQ = useQuery({ queryKey: ["messagesPerDay"], queryFn: getMessagesPerDay });
  const sessionQ = useOlxSession();
  const errorsQ = useQuery({
    queryKey: ["botErrors"],
    queryFn: getBotErrors,
    refetchInterval: 5000,
  });

  const clearErrors = useMutation({
    mutationFn: clearBotErrors,
    onSuccess: ({ cleared }) => {
      qc.setQueryData(["botErrors"], []);
      qc.setQueryData(["botStatus"], (current: typeof statusQ.data) =>
        current ? { ...current, errors_today: 0, last_error: null } : current,
      );
      setErrorsOpen(false);
      toast.success(cleared === 1 ? "Eroarea a fost ștearsă" : `${cleared} erori au fost șterse`);
    },
    onError: () => toast.error("Nu am putut șterge erorile"),
  });

  const connectOlx = useMutation({
    mutationFn: startOlxLogin,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["olxSession"] });
      toast.info("S-a deschis o fereastră de browser — loghează-te în contul OLX.");
    },
    onError: () => toast.error("Nu am putut deschide fereastra de login"),
  });

  const toggle = useMutation({
    mutationFn: async () => {
      if (statusQ.data?.running) {
        return { action: "stop" as const, status: await stopBot() };
      }
      return { action: "start" as const, status: await startBot() };
    },
    onSuccess: ({ action, status }) => {
      qc.setQueryData(["botStatus"], status);
      if (action === "start" && !status.running) {
        // erorile Playwright pot avea sute de caractere — nu umplem ecranul
        toast.error(truncate(status.last_error ?? "Botul nu a putut porni", 200));
      } else if (action === "stop" && status.stopping) {
        // oprirea nu e instantanee: botul termina ciclul curent (navigari,
        // pauze umane) si inchide browserul — poate dura zeci de secunde
        toast.info("Oprire în curs — botul termină ciclul curent…");
      } else {
        toast.success(status.running ? "Bot pornit" : "Bot oprit");
      }
    },
    onError: (e) =>
      toast.error(
        e instanceof Error && e.message
          ? truncate(e.message, 200)
          : "Nu am putut schimba starea botului",
      ),
  });

  const status = statusQ.data;
  const running = status?.running ?? false;
  const stopping = status?.stopping ?? false;
  const recent = (convosQ.data ?? []).slice(0, 5);
  const productsById = new Map((productsQ.data ?? []).map((p) => [p.id, p]));
  const messagesToday = (convosQ.data ?? []).flatMap((thread) =>
    thread.messages
      .filter((message) => {
        const timestamp = new Date(message.timestamp);
        const today = new Date();
        return (
          !Number.isNaN(timestamp.getTime()) && timestamp.toDateString() === today.toDateString()
        );
      })
      .map((message) => ({ thread, message })),
  );
  const session = sessionQ.data;
  const olxConnected = session?.connected ?? false;
  const loginRunning = session?.login_running ?? false;

  // cand fereastra de login se inchide, spunem clar cum s-a terminat
  const prevLoginRunning = useRef(false);
  useEffect(() => {
    if (prevLoginRunning.current && !loginRunning && session) {
      if (session.connected && session.account) {
        toast.success(`Cont conectat: ${accountDisplayName(session.account)}`);
      } else {
        toast.error("Fereastra de login s-a închis fără conectare — încearcă din nou.");
      }
    }
    prevLoginRunning.current = loginRunning;
  }, [loginRunning, session]);

  // O eroare noua deschide centrul o singura data. Poll-urile ulterioare nu
  // intrerup utilizatorul din nou pentru acelasi incident.
  useEffect(() => {
    const newest = errorsQ.data?.[0];
    if (newest && newest.id !== lastAutoOpenedError.current) {
      lastAutoOpenedError.current = newest.id;
      setErrorsOpen(true);
    }
  }, [errorsQ.data]);
  // OLX cere login manual (CAPTCHA); botul nu poate porni fara cont conectat.
  const loginRequired = !!status?.last_error?.includes("login.py") || (!!session && !olxConnected);

  return (
    <AppShell>
      <PageHeader title="Dashboard" description="Prezentare generală a activității botului OLX." />

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Status card — double-bezel enclosure */}
        <div
          className="reveal rounded-[1.65rem] bg-foreground/[0.035] p-1.5 ring-1 ring-foreground/[0.06] lg:col-span-1"
          style={{ "--i": 1 } as CSSProperties}
        >
          <div className="h-full rounded-[calc(1.65rem-0.375rem)] bg-card p-5 shadow-[inset_0_1px_1px_oklch(1_0_0/0.7),0_1px_2px_oklch(0.25_0.02_230/0.05)]">
            <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
              Stare bot
            </div>
            {statusQ.isLoading || !status ? (
              <Skeleton className="mt-4 h-28 w-full" />
            ) : (
              <div className="mt-4 space-y-4">
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "live-dot h-3 w-3 shrink-0 rounded-full",
                      stopping
                        ? "animate-pulse bg-amber-400"
                        : running
                          ? "bg-emerald-500"
                          : "bg-zinc-300",
                    )}
                  />
                  <div>
                    <div className="text-xl font-semibold tracking-tight">
                      {stopping ? "Se oprește…" : running ? "Bot pornit" : "Bot oprit"}
                    </div>
                    <div className="font-mono text-xs text-muted-foreground">
                      poll: {status.poll_interval_seconds}s
                    </div>
                  </div>
                </div>
                {/* Stare cont OLX + meniu de conturi (switch / adauga / sign out) */}
                <div className="flex items-center gap-2 rounded-xl border border-border/70 bg-muted/40 px-3 py-2 text-xs">
                  {olxConnected ? (
                    <CheckCircle2
                      className="h-3.5 w-3.5 shrink-0 text-emerald-500"
                      strokeWidth={1.5}
                    />
                  ) : (
                    <KeyRound className="h-3.5 w-3.5 shrink-0 text-amber-500" strokeWidth={1.5} />
                  )}
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">
                    {session?.account
                      ? `${accountDisplayName(session.account)}${olxConnected ? "" : " — neconectat"}`
                      : "Cont OLX neconectat"}
                  </span>
                  <AccountMenu align="end">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 shrink-0 gap-1 rounded-md px-1.5 text-[11px] font-medium text-muted-foreground"
                    >
                      Cont
                      <ChevronDown className="h-3 w-3" strokeWidth={1.5} />
                    </Button>
                  </AccountMenu>
                </div>

                {!olxConnected ? (
                  <div className="space-y-2.5">
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      OLX cere login manual (CAPTCHA). Apasă butonul, loghează-te o singură dată în
                      fereastra care se deschide, iar botul reține sesiunea.
                    </p>
                    <Button
                      size="lg"
                      className="group w-full justify-between rounded-full pl-6 pr-2"
                      disabled={connectOlx.isPending || loginRunning}
                      onClick={() => connectOlx.mutate()}
                    >
                      <span>{loginRunning ? "Se așteaptă login-ul…" : "Conectează cont OLX"}</span>
                      <span className="grid h-7 w-7 place-items-center rounded-full bg-white/15 transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:scale-110">
                        {loginRunning ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                        ) : (
                          <KeyRound className="h-3.5 w-3.5" strokeWidth={1.5} />
                        )}
                      </span>
                    </Button>
                  </div>
                ) : (
                  <>
                    {status.last_error && !loginRequired ? (
                      <div className="flex max-h-40 items-start gap-2 overflow-y-auto rounded-xl bg-red-50 p-2.5 text-xs leading-relaxed text-red-700 dark:bg-red-500/10 dark:text-red-300">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                        {/* min-w-0 + overflow-wrap:anywhere: erorile cu cai
                            lungi de fisiere nu mai ies din card */}
                        <span className="min-w-0 flex-1 whitespace-pre-wrap [overflow-wrap:anywhere]">
                          {status.last_error}
                        </span>
                      </div>
                    ) : null}
                    <Button
                      size="lg"
                      variant={running ? "destructive" : "default"}
                      className="group w-full justify-between rounded-full pl-6 pr-2"
                      disabled={toggle.isPending || stopping}
                      onClick={() => toggle.mutate()}
                    >
                      <span>
                        {stopping ? "Se oprește…" : running ? "Oprește botul" : "Pornește botul"}
                      </span>
                      <span className="grid h-7 w-7 place-items-center rounded-full bg-white/15 transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:scale-110">
                        {toggle.isPending || stopping ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                        ) : running ? (
                          <PowerOff className="h-3.5 w-3.5" strokeWidth={1.5} />
                        ) : (
                          <Power className="h-3.5 w-3.5" strokeWidth={1.5} />
                        )}
                      </span>
                    </Button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Stat cards */}
        <div className="grid gap-5 sm:grid-cols-2 lg:col-span-2">
          <StatCard
            index={2}
            label="Mesaje azi"
            value={status?.messages_today}
            loading={statusQ.isLoading}
            icon={<MessagesSquare className="h-4 w-4" strokeWidth={1.5} />}
            onClick={() => setDetailsOpen("messages")}
          />
          <StatCard
            index={3}
            label="Erori azi"
            value={status?.errors_today}
            loading={statusQ.isLoading}
            icon={<AlertTriangle className="h-4 w-4" strokeWidth={1.5} />}
            tone={status && status.errors_today > 0 ? "warn" : "default"}
            onClick={() => setErrorsOpen(true)}
          />
          <StatCard
            index={4}
            label="Produse în catalog"
            value={productsQ.data?.length}
            loading={productsQ.isLoading}
            icon={<Package className="h-4 w-4" strokeWidth={1.5} />}
            onClick={() => setDetailsOpen("products")}
          />
          <StatCard
            index={5}
            label="Ultimul poll"
            valueText={status ? timeAgo(status.last_poll) : undefined}
            loading={statusQ.isLoading}
            icon={<Clock className="h-4 w-4" strokeWidth={1.5} />}
            onClick={() => setDetailsOpen("poll")}
          />
        </div>
      </div>

      {/* Chart */}
      <Card className="reveal mt-5" style={{ "--i": 6 } as CSSProperties}>
        <CardHeader>
          <CardTitle className="text-base tracking-tight">
            Mesaje pe zi
            <span className="ml-2 text-xs font-normal text-muted-foreground">ultimele 7 zile</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {chartQ.isLoading || !chartQ.data ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartQ.data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="fillMesaje" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v) =>
                      new Date(v).toLocaleDateString("ro-RO", { weekday: "short" })
                    }
                    stroke="var(--muted-foreground)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    stroke="var(--muted-foreground)"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    cursor={{ stroke: "var(--border)" }}
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: 12,
                      fontSize: 12,
                      boxShadow: "0 16px 40px -18px oklch(0.25 0.02 230 / 0.2)",
                    }}
                    labelFormatter={(v) => new Date(v as string).toLocaleDateString("ro-RO")}
                    formatter={(v) => [v, "Mesaje"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="var(--primary)"
                    strokeWidth={2.5}
                    fill="url(#fillMesaje)"
                    dot={false}
                    activeDot={{ r: 5, strokeWidth: 0 }}
                    animationDuration={900}
                    animationEasing="ease-out"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent conversations */}
      <Card className="reveal mt-5" style={{ "--i": 7 } as CSSProperties}>
        <CardHeader>
          <CardTitle className="text-base tracking-tight">Conversații recente</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {convosQ.isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              Încă nicio conversație. Pornește botul și mesajele vor apărea aici.
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {recent.map((t, i) => {
                const last = t.messages[t.messages.length - 1];
                const product = t.product_id ? productsById.get(t.product_id) : null;
                const adTitle = t.ad_title ?? product?.title;
                return (
                  <li
                    key={t.olx_conversation_id}
                    className="reveal"
                    style={{ "--i": 8 + i } as CSSProperties}
                  >
                    <button
                      type="button"
                      onClick={() =>
                        navigate({
                          to: "/conversations",
                          search: { conversation: t.olx_conversation_id },
                        })
                      }
                      className="group flex w-full items-start gap-3 px-5 py-3.5 text-left transition-colors duration-300 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                      aria-label={`Deschide conversația cu ${t.buyer_name ?? "cumpărătorul"}`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span className="font-mono">{formatDateTime(t.last_timestamp)}</span>
                          <span>·</span>
                          <span className="truncate font-medium text-foreground">
                            {t.buyer_name ?? "Cumpărător"}
                          </span>
                          {adTitle ? (
                            <>
                              <span>·</span>
                              <span className="truncate">{adTitle}</span>
                            </>
                          ) : null}
                          {t.messages.length > 1 ? (
                            <span className="ml-auto shrink-0 rounded-full bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                              {t.messages.length} mesaje
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-1 truncate text-sm font-medium">
                          {last ? truncate(last.buyer_message, 80) : "—"}
                        </div>
                        <div className="truncate text-sm text-muted-foreground">
                          {last?.bot_response ? truncate(last.bot_response, 100) : "—"}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {last ? <StatusBadge status={last.status} /> : null}
                        <ArrowUpRight
                          className="h-4 w-4 text-muted-foreground transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-foreground"
                          strokeWidth={1.5}
                        />
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Dialog open={detailsOpen !== null} onOpenChange={(open) => !open && setDetailsOpen(null)}>
        <DialogContent className="max-h-[min(82vh,720px)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden p-0 sm:max-w-2xl sm:rounded-[1.5rem]">
          <DialogHeader className="border-b border-border/70 bg-muted/25 px-6 pb-5 pt-6 text-left">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/15">
                {detailsOpen === "messages" ? (
                  <MessagesSquare className="h-5 w-5" strokeWidth={1.5} />
                ) : detailsOpen === "products" ? (
                  <Package className="h-5 w-5" strokeWidth={1.5} />
                ) : (
                  <Clock className="h-5 w-5" strokeWidth={1.5} />
                )}
              </span>
              <div>
                <DialogTitle className="text-xl">
                  {detailsOpen === "messages"
                    ? "Mesaje procesate azi"
                    : detailsOpen === "products"
                      ? "Produse în catalog"
                      : "Ultimul poll"}
                </DialogTitle>
                <DialogDescription className="mt-1">
                  {detailsOpen === "messages"
                    ? `${messagesToday.length} ${messagesToday.length === 1 ? "mesaj înregistrat" : "mesaje înregistrate"}`
                    : detailsOpen === "products"
                      ? `${productsQ.data?.length ?? 0} ${(productsQ.data?.length ?? 0) === 1 ? "produs disponibil" : "produse disponibile"}`
                      : "Detaliile ultimei verificări automate OLX"}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          <div className="min-h-0 overflow-y-auto px-6 py-5">
            {detailsOpen === "messages" ? (
              messagesToday.length ? (
                <ol className="space-y-3">
                  {messagesToday.map(({ thread, message }) => (
                    <li key={`${thread.olx_conversation_id}-${message.id}`}>
                      <button
                        type="button"
                        onClick={() => {
                          setDetailsOpen(null);
                          navigate({
                            to: "/conversations",
                            search: { conversation: thread.olx_conversation_id },
                          });
                        }}
                        className="group w-full rounded-2xl border border-border/80 bg-muted/25 p-4 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                          <span className="truncate font-medium text-foreground">
                            {thread.buyer_name ?? "Cumpărător"}
                          </span>
                          <time className="shrink-0 font-mono text-[11px]">
                            {formatDateTime(message.timestamp)}
                          </time>
                        </div>
                        <div className="mt-2 line-clamp-2 text-sm">{message.buyer_message}</div>
                        <div className="mt-2 flex items-center justify-between gap-3">
                          <span className="truncate text-xs text-muted-foreground">
                            {thread.ad_title ?? "Anunț nespecificat"}
                          </span>
                          <StatusBadge status={message.status} />
                        </div>
                      </button>
                    </li>
                  ))}
                </ol>
              ) : (
                <DialogEmptyState text="Nu există mesaje procesate astăzi." />
              )
            ) : detailsOpen === "products" ? (
              productsQ.data?.length ? (
                <ol className="grid gap-3 sm:grid-cols-2">
                  {productsQ.data.map((product) => (
                    <li key={product.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setDetailsOpen(null);
                          navigate({
                            to: "/products/$productId",
                            params: { productId: product.id },
                          });
                        }}
                        className="group h-full w-full rounded-2xl border border-border/80 bg-muted/25 p-4 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate font-medium">{product.title}</div>
                            <div className="mt-1 truncate text-xs text-muted-foreground">
                              {product.category} · {product.subcategory}
                            </div>
                          </div>
                          <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                        </div>
                        <div className="mt-4 flex items-end justify-between gap-3">
                          <span className="font-mono text-sm font-semibold">
                            {formatPrice(product.price, product.currency)}
                          </span>
                          <span className="rounded-full bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground ring-1 ring-border">
                            stoc {product.stock}
                          </span>
                        </div>
                      </button>
                    </li>
                  ))}
                </ol>
              ) : (
                <DialogEmptyState text="Catalogul nu conține încă produse." />
              )
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <PollDetail
                  label="Ultima verificare"
                  value={status?.last_poll ? formatDateTime(status.last_poll) : "Nicio verificare"}
                />
                <PollDetail
                  label="Stare bot"
                  value={stopping ? "Se oprește" : running ? "Pornit" : "Oprit"}
                />
                <PollDetail
                  label="Interval"
                  value={`${status?.poll_interval_seconds ?? "—"} secunde`}
                />
                <PollDetail
                  label="Următoarea verificare"
                  value={
                    running && status?.last_poll
                      ? formatDateTime(
                          new Date(
                            new Date(status.last_poll).getTime() +
                              status.poll_interval_seconds * 1000,
                          ).toISOString(),
                        )
                      : "—"
                  }
                />
              </div>
            )}
          </div>

          <DialogFooter className="border-t border-border/70 bg-muted/20 px-6 py-4">
            <Button variant="ghost" onClick={() => setDetailsOpen(null)}>
              Închide
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={errorsOpen} onOpenChange={setErrorsOpen}>
        <DialogContent className="max-h-[min(82vh,720px)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden border-red-200/70 bg-card p-0 shadow-[0_30px_90px_-30px_oklch(0.45_0.2_25/0.35)] dark:border-red-500/20 sm:max-w-2xl sm:rounded-[1.5rem]">
          <DialogHeader className="border-b border-border/70 bg-red-50/70 px-6 pb-5 pt-6 text-left dark:bg-red-500/[0.07]">
            <div className="mb-3 flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-red-100 text-red-700 ring-1 ring-red-200 dark:bg-red-500/15 dark:text-red-300 dark:ring-red-500/25">
                <AlertTriangle className="h-5 w-5" strokeWidth={1.5} />
              </span>
              <div>
                <DialogTitle className="text-xl">Centrul de erori</DialogTitle>
                <DialogDescription className="mt-1">
                  {errorsQ.data?.length
                    ? `${errorsQ.data.length} ${errorsQ.data.length === 1 ? "incident înregistrat" : "incidente înregistrate"} azi`
                    : "Nu există erori active"}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            {errorsQ.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </div>
            ) : errorsQ.data?.length ? (
              <ol className="space-y-3">
                {errorsQ.data.map((error, index) => (
                  <li
                    key={error.id}
                    className="rounded-2xl border border-border/80 bg-muted/30 p-4"
                  >
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-red-600 dark:text-red-300">
                        Incident {errorsQ.data.length - index}
                      </span>
                      <time className="shrink-0 font-mono text-[11px] text-muted-foreground">
                        {formatDateTime(error.timestamp)}
                      </time>
                    </div>
                    <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground [overflow-wrap:anywhere]">
                      {error.message}
                    </pre>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="grid min-h-48 place-items-center text-center">
                <div>
                  <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                    <CheckCircle2 className="h-6 w-6" strokeWidth={1.5} />
                  </span>
                  <div className="mt-4 font-medium">Totul este în regulă</div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Erorile noi vor apărea automat aici.
                  </p>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="flex-row items-center justify-between border-t border-border/70 bg-muted/20 px-6 py-4 sm:justify-between sm:space-x-0">
            <Button variant="ghost" onClick={() => setErrorsOpen(false)}>
              Închide
            </Button>
            <Button
              variant="destructive"
              className="gap-2 rounded-full"
              disabled={!errorsQ.data?.length || clearErrors.isPending}
              onClick={() => clearErrors.mutate()}
            >
              {clearErrors.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" strokeWidth={1.5} />
              )}
              Șterge erorile
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}

function DialogEmptyState({ text }: { text: string }) {
  return (
    <div className="grid min-h-48 place-items-center text-center">
      <div>
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-muted text-muted-foreground">
          <CheckCircle2 className="h-6 w-6" strokeWidth={1.5} />
        </span>
        <p className="mt-4 text-sm text-muted-foreground">{text}</p>
      </div>
    </div>
  );
}

function PollDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/80 bg-muted/25 p-4">
      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 font-mono text-sm font-semibold">{value}</div>
    </div>
  );
}

function StatCard({
  index,
  label,
  value,
  valueText,
  loading,
  icon,
  tone = "default",
  onClick,
}: {
  index: number;
  label: string;
  value?: number;
  valueText?: string;
  loading?: boolean;
  icon?: React.ReactNode;
  tone?: "default" | "warn";
  onClick?: () => void;
}) {
  const card = (
    <Card
      className={cn("reveal hover-lift", onClick && "cursor-pointer")}
      style={{ "--i": index } as CSSProperties}
      onClick={onClick}
    >
      <CardContent className="p-5">
        <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
          <span className="uppercase tracking-[0.14em] text-[10px]">{label}</span>
          <span
            className={cn(
              "grid h-7 w-7 place-items-center rounded-lg",
              tone === "warn"
                ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
                : "bg-muted text-muted-foreground",
            )}
          >
            {icon}
          </span>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-8 w-24" />
        ) : (
          <div className="mt-2 font-mono text-[1.7rem] font-semibold leading-none tracking-tight tabular-nums">
            {valueText ?? value ?? "—"}
          </div>
        )}
      </CardContent>
    </Card>
  );
  if (!onClick) return card;
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Deschide ${label.toLowerCase()}`}
      className="rounded-[var(--radius)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
    >
      {card}
    </div>
  );
}
