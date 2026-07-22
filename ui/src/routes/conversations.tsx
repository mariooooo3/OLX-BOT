import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Search, MessagesSquare, User } from "lucide-react";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState } from "@/components/empty-state";
import { getConversations, getProducts } from "@/lib/api";
import { AccountBadge, accountBorderClass, scopeLabel } from "@/components/account-scope";
import { ALL_ACCOUNTS, useAccountScope, useAccounts, findAccount } from "@/lib/accounts";
import type { ConversationThread } from "@/lib/types";
import { formatDateTime, truncate, formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/conversations")({
  validateSearch: (search: Record<string, unknown>) => ({
    conversation:
      typeof search.conversation === "string" && search.conversation
        ? search.conversation
        : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Conversații — OLX Bot" },
      { name: "description", content: "Istoricul conversațiilor gestionate de botul OLX." },
    ],
  }),
  component: ConversationsPage,
});

/** Numele afisat al interlocutorului (intrarile vechi nu au numele salvat). */
export function buyerLabel(t: ConversationThread) {
  return t.buyer_name ?? "Cumpărător";
}

/** Identificatorul unui fir. Include contul: acelasi id de conversatie OLX
 *  poate exista pe doua conturi diferite. */
export function threadKey(t: ConversationThread) {
  return `${t.account_id}:${t.olx_conversation_id}`;
}

function lastMessage(t: ConversationThread) {
  return t.messages[t.messages.length - 1];
}

function ConversationsPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  // scope-ul e partajat cu celelalte module si tinut minte intre navigari
  const [scope] = useAccountScope();
  const { accounts } = useAccounts();
  // cerem serverului direct conturile din scope: un cont fara mesaje intoarce
  // o lista goala, ceea ce e un raspuns valid, nu o eroare
  const convosQ = useQuery({
    queryKey: ["conversations", scope],
    queryFn: () => getConversations(scope === ALL_ACCOUNTS ? undefined : scope),
  });
  const productsQ = useQuery({ queryKey: ["products"], queryFn: () => getProducts() });

  const [status, setStatus] = useState<string>("all");
  const [productId, setProductId] = useState<string>("all");
  const [q, setQ] = useState("");

  const productsById = useMemo(
    () => new Map((productsQ.data ?? []).map((p) => [p.id, p])),
    [productsQ.data],
  );

  const filtered = useMemo(() => {
    let list = convosQ.data ?? [];
    if (status !== "all") list = list.filter((t) => lastMessage(t)?.status === status);
    if (productId !== "all") list = list.filter((t) => (t.product_id ?? "none") === productId);
    if (q.trim()) {
      const needle = q.toLowerCase();
      list = list.filter(
        (t) =>
          (t.buyer_name ?? "").toLowerCase().includes(needle) ||
          (t.ad_title ?? "").toLowerCase().includes(needle) ||
          t.messages.some(
            (m) =>
              m.buyer_message.toLowerCase().includes(needle) ||
              m.bot_response.toLowerCase().includes(needle),
          ),
      );
    }
    return list;
  }, [convosQ.data, status, productId, q]);

  // firul selectat se ia mereu din datele proaspete, ca sa apara si
  // mesajele sosite dupa deschiderea panoului
  // acceptam si id-ul simplu al conversatiei (linkuri vechi, dinainte de
  // conturile multiple), nu doar cheia completa "<cont>:<conversatie>"
  const selected =
    (convosQ.data ?? []).find(
      (t) => threadKey(t) === search.conversation || t.olx_conversation_id === search.conversation,
    ) ?? null;
  const loading = convosQ.isLoading || productsQ.isLoading;
  const scopeName = scopeLabel(scope, accounts);
  /** culoarea contului unui fir, pentru bara si eticheta colorata */
  const colorOf = (t: ConversationThread) => findAccount(accounts, t.account_id)?.color;
  const selectedProduct = selected?.product_id ? productsById.get(selected.product_id) : null;

  return (
    <AppShell>
      <PageHeader
        title="Conversații"
        description="Fiecare conversație cu istoricul complet al mesajelor și răspunsurilor."
      />

      <Card className="reveal mb-5" style={{ "--i": 1 } as React.CSSProperties}>
        <CardContent className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_180px_220px]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Caută după nume, anunț sau mesaj..."
              className="pl-9"
            />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger>
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toate statusurile</SelectItem>
              <SelectItem value="sent">Trimis</SelectItem>
              <SelectItem value="failed">Eșuat</SelectItem>
              <SelectItem value="pending">În așteptare</SelectItem>
            </SelectContent>
          </Select>
          <Select value={productId} onValueChange={setProductId}>
            <SelectTrigger>
              <SelectValue placeholder="Produs" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toate produsele</SelectItem>
              <SelectItem value="none">Fără produs asociat</SelectItem>
              {(productsQ.data ?? []).map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {truncate(p.title, 40)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card className="reveal" style={{ "--i": 2 } as React.CSSProperties}>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<MessagesSquare className="h-6 w-6" />}
              title={
                scopeName ? `Nicio conversație pe contul ${scopeName}` : "Nicio conversație găsită"
              }
              description={
                scopeName
                  ? `Contul ${scopeName} nu a primit încă mesaje. Alege alt cont sau „Toate conturile”.`
                  : "Ajustează filtrele sau așteaptă noi mesaje de la cumpărători."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Ultima activitate</th>
                    <th className="px-4 py-3 font-medium">Cont</th>
                    <th className="px-4 py-3 font-medium">Utilizator</th>
                    <th className="px-4 py-3 font-medium">Anunț</th>
                    <th className="px-4 py-3 font-medium">Ultimul mesaj</th>
                    <th className="px-4 py-3 text-center font-medium">Mesaje</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t) => {
                    const last = lastMessage(t);
                    return (
                      <tr
                        key={threadKey(t)}
                        onClick={() =>
                          navigate({
                            search: { conversation: threadKey(t) },
                          })
                        }
                        className={cn(
                          "cursor-pointer border-b border-border last:border-0",
                          "transition-colors duration-300 hover:bg-muted/40 active:bg-muted/60",
                          // bara colorata = contul de pe care vine mesajul;
                          // nu coloram tot randul, ca sa nu se bata cu statusul
                          accountBorderClass(colorOf(t)),
                        )}
                      >
                        <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                          {formatDateTime(t.last_timestamp)}
                        </td>
                        <td className="px-4 py-3 max-w-[150px]">
                          <AccountBadge
                            account={{
                              display_name: t.account_label,
                              color: colorOf(t),
                            }}
                          />
                        </td>
                        <td className="px-4 py-3 max-w-[160px]">
                          <div className="truncate font-medium">{buyerLabel(t)}</div>
                        </td>
                        <td className="px-4 py-3 max-w-[200px]">
                          <div className="truncate text-muted-foreground">{t.ad_title ?? "—"}</div>
                        </td>
                        <td className="px-4 py-3 max-w-[280px]">
                          <div className="truncate">
                            {last ? truncate(last.buyer_message, 70) : "—"}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-center font-mono text-xs tabular-nums text-muted-foreground">
                          {t.messages.length}
                        </td>
                        <td className="px-4 py-3">
                          {last ? <StatusBadge status={last.status} /> : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Sheet
        open={!!selected}
        onOpenChange={(open) => !open && navigate({ search: { conversation: undefined } })}
      >
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-muted">
                <User className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
              </span>
              <span className="min-w-0">
                <span className="block truncate">{selected ? buyerLabel(selected) : ""}</span>
                {selected?.ad_title ? (
                  <span className="block truncate text-xs font-normal text-muted-foreground">
                    {selected.ad_title}
                  </span>
                ) : null}
                {selected ? (
                  <AccountBadge
                    className="mt-1"
                    account={{
                      display_name: selected.account_label,
                      color: colorOf(selected),
                    }}
                  />
                ) : null}
              </span>
            </SheetTitle>
            <SheetDescription>
              {selected
                ? `${selected.messages.length} ${selected.messages.length === 1 ? "mesaj" : "mesaje"} · ultima activitate ${formatDateTime(selected.last_timestamp)}`
                : ""}
            </SheetDescription>
          </SheetHeader>

          {selected ? (
            <div className="mt-4 space-y-5 px-4 pb-6">
              {/* istoricul complet, cronologic — ca un chat obisnuit */}
              <div className="space-y-4">
                {selected.messages.map((m) => (
                  <div key={m.id} className="space-y-3">
                    <div className="text-center font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                      {formatDateTime(m.timestamp)}
                    </div>
                    <div className="flex justify-start">
                      <div className="min-w-0 max-w-[85%] rounded-2xl rounded-tl-sm bg-muted px-4 py-2.5 text-sm [overflow-wrap:anywhere]">
                        <div className="mb-0.5 text-xs font-medium text-muted-foreground">
                          {buyerLabel(selected)}
                        </div>
                        {m.buyer_message}
                      </div>
                    </div>
                    {m.bot_response ? (
                      <div className="flex justify-end">
                        <div className="min-w-0 max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground [overflow-wrap:anywhere]">
                          <div className="mb-0.5 flex items-center justify-between gap-3 text-xs font-medium opacity-80">
                            <span>Bot</span>
                            <StatusBadge status={m.status} />
                          </div>
                          {m.bot_response}
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
                        Botul nu a răspuns la acest mesaj.
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="rounded-lg border border-border p-4">
                <div className="text-xs font-medium uppercase text-muted-foreground">
                  Produs asociat din catalog
                </div>
                {selectedProduct ? (
                  <div className="mt-2 space-y-1">
                    <div className="text-sm font-semibold">{selectedProduct.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {selectedProduct.category} · {selectedProduct.subcategory}
                    </div>
                    <div className="text-sm">
                      {formatPrice(selectedProduct.price, selectedProduct.currency)} · stoc{" "}
                      {selectedProduct.stock}
                    </div>
                  </div>
                ) : (
                  <div className="mt-2 text-sm text-muted-foreground">Fără produs asociat.</div>
                )}
              </div>

              <div className="font-mono text-[10px] text-muted-foreground">
                ID conversație OLX: {selected.olx_conversation_id}
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </AppShell>
  );
}
