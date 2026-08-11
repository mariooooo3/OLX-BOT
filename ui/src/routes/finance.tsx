import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  CalendarDays,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Landmark,
  PackageOpen,
  Plus,
  ReceiptText,
  Sparkles,
  Trash2,
  TrendingUp,
  WalletCards,
} from "lucide-react";
import { toast } from "sonner";

import { AccountBadge } from "@/components/account-scope";
import { AppShell, PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { deleteFinanceTransaction, getFinance, saveFinanceTransaction } from "@/lib/api";
import { ALL_ACCOUNTS, findAccount, useAccountScope, useAccounts } from "@/lib/accounts";
import { formatMoney } from "@/lib/format";
import type {
  FinanceCurrencySummary,
  FinanceReport,
  FinanceTransaction,
  FinanceTransactionInput,
  FinanceTransactionKind,
  ProductFinance,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/finance")({
  head: () => ({
    meta: [
      { title: "Gestiune — OLX Bot" },
      {
        name: "description",
        content: "Achiziții, vânzări, costuri și profitabilitate pe produs.",
      },
    ],
  }),
  component: FinancePage,
});

const KIND_META = {
  purchase: {
    label: "Achiziție",
    action: "Adaugă achiziție",
    icon: ArrowDownToLine,
    tone: "text-sky-700 bg-sky-100 dark:text-sky-300 dark:bg-sky-500/15",
  },
  sale: {
    label: "Vânzare",
    action: "Adaugă vânzare",
    icon: ArrowUpFromLine,
    tone: "text-emerald-700 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-500/15",
  },
  expense: {
    label: "Cost",
    action: "Adaugă cost",
    icon: ReceiptText,
    tone: "text-amber-700 bg-amber-100 dark:text-amber-300 dark:bg-amber-500/15",
  },
} satisfies Record<
  FinanceTransactionKind,
  { label: string; action: string; icon: typeof ArrowDownToLine; tone: string }
>;

function localToday() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

type FinanceMoneyField =
  | "cash_balance"
  | "invested"
  | "sales_revenue"
  | "realized_profit"
  | "inventory_value"
  | "projected_profit";

function formatReportMoney(report: FinanceReport | undefined, field: FinanceMoneyField) {
  const summaries = report?.currency_summaries ?? [];
  if (!summaries.length) return formatMoney(0);
  return summaries.map((item) => formatMoney(item[field], item.currency)).join(" · ");
}

function reportMoneyIsPositive(report: FinanceReport | undefined, field: FinanceMoneyField) {
  return (report?.currency_summaries ?? []).every((item) => item[field] >= 0);
}

function FinancePage() {
  const qc = useQueryClient();
  const [scope] = useAccountScope();
  const { accounts } = useAccounts();
  const scoped = scope === ALL_ACCOUNTS ? undefined : scope;
  const reportQ = useQuery({
    queryKey: ["finance", scope],
    queryFn: () => getFinance(scoped),
  });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<FinanceTransaction | null>(null);

  const save = useMutation({
    mutationFn: ({ input, accountId }: { input: FinanceTransactionInput; accountId?: string }) =>
      saveFinanceTransaction(input, accountId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance"] });
      setDialogOpen(false);
      toast.success("Mișcare înregistrată");
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Nu am putut salva mișcarea"),
  });

  const remove = useMutation({
    mutationFn: (transaction: FinanceTransaction) =>
      deleteFinanceTransaction(transaction.id, transaction.account_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance"] });
      setPendingDelete(null);
      toast.success("Mișcare ștearsă");
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Nu am putut șterge mișcarea"),
  });

  if (reportQ.isLoading) {
    return (
      <AppShell>
        <PageHeader
          title="Gestiune"
          description="Balanță, stoc financiar și randament pe produs."
        />
        <FinanceSkeleton />
      </AppShell>
    );
  }

  if (reportQ.isError) {
    const message =
      reportQ.error instanceof Error
        ? reportQ.error.message
        : "Nu am putut încărca informațiile de gestiune.";
    return (
      <AppShell>
        <PageHeader
          title="Gestiune"
          description="Balanță, stoc financiar și randament pe produs."
        />
        <EmptyState
          icon={<Landmark className="h-6 w-6" />}
          title="Gestiunea nu poate fi afișată"
          description={message}
        />
      </AppShell>
    );
  }

  const report = reportQ.data;
  const products = report?.products ?? [];
  const summary = report?.summary;

  return (
    <AppShell>
      <PageHeader
        title="Gestiune"
        description="Registrul achizițiilor, vânzărilor și costurilor produselor."
        actions={
          <Button disabled={!products.length} onClick={() => setDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Înregistrează
          </Button>
        }
      />

      {!report || !products.length ? (
        <EmptyState
          icon={<PackageOpen className="h-6 w-6" />}
          title="Gestiunea începe cu un produs"
          description="Adaugă întâi produsul în catalog, apoi îi poți înregistra achizițiile, vânzările și costurile."
          action={
            <Button asChild>
              <Link
                to="/products/$productId"
                params={{ productId: "new" }}
                search={{ account: scoped }}
              >
                <Plus className="mr-2 h-4 w-4" />
                Adaugă produs
              </Link>
            </Button>
          }
        />
      ) : (
        <>
          <section className="grid gap-5 lg:grid-cols-[1.15fr_1.85fr]">
            <BalanceCard
              cashBalance={formatReportMoney(report, "cash_balance")}
              invested={formatReportMoney(report, "invested")}
              revenue={formatReportMoney(report, "sales_revenue")}
              negative={!reportMoneyIsPositive(report, "cash_balance")}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <MetricCard
                index={2}
                label="Profit realizat"
                value={formatReportMoney(report, "realized_profit")}
                detail="După costul unităților vândute și costurile suplimentare"
                icon={<TrendingUp className="h-4 w-4" />}
                positive={reportMoneyIsPositive(report, "realized_profit")}
              />
              <MetricCard
                index={3}
                label="Valoare în stoc"
                value={formatReportMoney(report, "inventory_value")}
                detail={`${summary?.stock_quantity ?? 0} bucăți nevândute`}
                icon={<PackageOpen className="h-4 w-4" />}
              />
              <MetricCard
                index={4}
                label="Rată de vânzare"
                value={`${summary?.sell_through_rate ?? 0}%`}
                detail={`${summary?.sold_quantity ?? 0} din ${summary?.purchase_quantity ?? 0} bucăți`}
                icon={<Sparkles className="h-4 w-4" />}
              />
              <MetricCard
                index={5}
                label="Profit potențial"
                value={formatReportMoney(report, "projected_profit")}
                detail="Dacă stocul rămas se vinde la prețul actual"
                icon={<CircleDollarSign className="h-4 w-4" />}
                positive={reportMoneyIsPositive(report, "projected_profit")}
              />
            </div>
          </section>

          <section className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.85fr)]">
            <ProductPerformance products={products} accounts={accounts} />
            <VatCard summaries={report.currency_summaries} />
          </section>

          <Ledger
            transactions={report.transactions}
            onAdd={() => setDialogOpen(true)}
            onDelete={setPendingDelete}
          />
        </>
      )}

      <TransactionDialog
        open={dialogOpen}
        products={products}
        saving={save.isPending}
        onOpenChange={setDialogOpen}
        onSubmit={(input, accountId) => save.mutate({ input, accountId })}
      />

      <Dialog open={!!pendingDelete} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Ștergi mișcarea?</DialogTitle>
            <DialogDescription>
              Calculele produsului „{pendingDelete?.product_title}” vor fi refăcute imediat.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDelete(null)}>
              Renunță
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => pendingDelete && remove.mutate(pendingDelete)}
            >
              Șterge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}

function BalanceCard({
  cashBalance,
  invested,
  revenue,
  negative,
}: {
  cashBalance: string;
  invested: string;
  revenue: string;
  negative: boolean;
}) {
  return (
    <Card
      className="reveal relative overflow-hidden border-0 bg-[oklch(0.25_0.035_205)] text-white shadow-[0_24px_60px_-30px_oklch(0.25_0.08_200/0.75)] dark:bg-[oklch(0.25_0.035_205)]"
      style={{ "--i": 1 } as CSSProperties}
    >
      <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full border-[36px] border-white/[0.045]" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-28 w-44 bg-[radial-gradient(circle_at_bottom_right,oklch(0.72_0.13_175/0.28),transparent_68%)]" />
      <CardContent className="relative flex min-h-64 flex-col p-6 sm:p-7">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/55">
            Balanță curentă
          </span>
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 ring-1 ring-white/15">
            <WalletCards className="h-4 w-4 text-white/85" strokeWidth={1.5} />
          </span>
        </div>
        <div
          className={cn(
            "mt-7 font-mono text-[clamp(2rem,5vw,3.2rem)] font-semibold leading-none tracking-[-0.05em] tabular-nums",
            negative ? "text-amber-200" : "text-emerald-200",
          )}
        >
          {cashBalance}
        </div>
        <p className="mt-3 max-w-sm text-xs leading-relaxed text-white/55">
          Încasări minus toate achizițiile și costurile înregistrate. Stocul nevândut rămâne activ
          separat.
        </p>
        <div className="mt-auto grid grid-cols-2 gap-4 border-t border-white/10 pt-5">
          <BalanceDetail label="Capital investit" value={invested} />
          <BalanceDetail label="Încasări nete" value={revenue} />
        </div>
      </CardContent>
    </Card>
  );
}

function BalanceDetail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-white/40">
        {label}
      </div>
      <div className="mt-1.5 font-mono text-sm font-semibold tabular-nums text-white/90">
        {value}
      </div>
    </div>
  );
}

function MetricCard({
  index,
  label,
  value,
  detail,
  icon,
  positive,
}: {
  index: number;
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
  positive?: boolean;
}) {
  return (
    <Card className="reveal hover-lift" style={{ "--i": index } as CSSProperties}>
      <CardContent className="flex h-full min-h-32 flex-col p-5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            {label}
          </span>
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-muted text-muted-foreground">
            {icon}
          </span>
        </div>
        <div
          className={cn(
            "mt-3 font-mono text-2xl font-semibold tracking-tight tabular-nums",
            positive === true && "text-emerald-700 dark:text-emerald-300",
            positive === false && "text-amber-700 dark:text-amber-300",
          )}
        >
          {value}
        </div>
        <p className="mt-auto pt-2 text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  );
}

function ProductPerformance({
  products,
  accounts,
}: {
  products: ProductFinance[];
  accounts: ReturnType<typeof useAccounts>["accounts"];
}) {
  const [selectedProduct, setSelectedProduct] = useState<ProductFinance | null>(null);

  return (
    <>
      <Card className="reveal" style={{ "--i": 6 } as CSSProperties}>
        <CardHeader className="border-b border-border/70 pb-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="font-display text-base">Randament pe produs</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Produsele sunt ordonate după profitul realizat.
              </p>
            </div>
            <span className="rounded-full bg-muted px-3 py-1 font-mono text-[10px] text-muted-foreground">
              {products.length} {products.length === 1 ? "produs" : "produse"}
            </span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-border/70">
            {products.map((product, index) => (
              <button
                type="button"
                key={`${product.account_id ?? ""}:${product.product_id}`}
                className="grid w-full gap-4 px-5 py-5 text-left transition-colors hover:bg-muted/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:grid-cols-[minmax(0,1.5fr)_minmax(150px,0.8fr)_auto]"
                onClick={() => setSelectedProduct(product)}
              >
                <div className="flex min-w-0 gap-3">
                  <span className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">{product.title}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <AccountBadge
                        account={{
                          display_name: product.account_label,
                          color: findAccount(accounts, product.account_id)?.color,
                        }}
                      />
                      <span className="text-[11px] text-muted-foreground">
                        {product.sold_quantity}/{product.purchase_quantity} vândute
                      </span>
                      {product.average_days_to_sale !== null ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Clock3 className="h-3 w-3" />
                          {product.average_days_to_sale} zile
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>
                <div className="self-center">
                  <div className="flex items-center justify-between font-mono text-[10px] text-muted-foreground">
                    <span>Rată vânzare</span>
                    <span>{product.sell_through_rate}%</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out"
                      style={{ width: `${Math.min(product.sell_through_rate, 100)}%` }}
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 sm:min-w-36 sm:justify-end sm:text-right">
                  <div>
                    <div
                      className={cn(
                        "font-mono text-sm font-semibold tabular-nums",
                        product.realized_profit >= 0
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-amber-700 dark:text-amber-300",
                      )}
                    >
                      {formatMoney(product.realized_profit, product.currency)}
                    </div>
                    <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                      ROI {product.roi}%
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
      <ProductFinanceDialog
        product={selectedProduct}
        accountColor={findAccount(accounts, selectedProduct?.account_id)?.color}
        onOpenChange={(open) => !open && setSelectedProduct(null)}
      />
    </>
  );
}

function ProductFinanceDialog({
  product,
  accountColor,
  onOpenChange,
}: {
  product: ProductFinance | null;
  accountColor?: number;
  onOpenChange: (open: boolean) => void;
}) {
  if (!product) return null;

  const details = [
    ["Capital investit", formatMoney(product.invested, product.currency)],
    ["Încasări nete", formatMoney(product.sales_revenue, product.currency)],
    ["Profit realizat", formatMoney(product.realized_profit, product.currency)],
    ["Profit potențial", formatMoney(product.projected_profit, product.currency)],
    ["Valoare în stoc", formatMoney(product.inventory_value, product.currency)],
    ["Costuri suplimentare", formatMoney(product.additional_costs, product.currency)],
    ["Preț mediu achiziție", formatMoney(product.average_purchase_price, product.currency)],
    ["Preț mediu vânzare", formatMoney(product.average_sale_price, product.currency)],
    ["TVA colectat", formatMoney(product.sales_vat, product.currency)],
    ["TVA recuperabil", formatMoney(product.recoverable_vat, product.currency)],
  ];

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2 pr-8">
            <AccountBadge account={{ display_name: product.account_label, color: accountColor }} />
          </div>
          <DialogTitle className="font-display text-xl">{product.title}</DialogTitle>
          <DialogDescription>
            Balanța completă și randamentul calculat din registrul acestui produs.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-2xl bg-[oklch(0.25_0.035_205)] p-5 text-white">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/50">
            Balanță curentă
          </div>
          <div
            className={cn(
              "mt-2 font-mono text-3xl font-semibold tracking-tight tabular-nums",
              product.cash_balance < 0 ? "text-amber-200" : "text-emerald-200",
            )}
          >
            {formatMoney(product.cash_balance, product.currency)}
          </div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-white/10 pt-4 text-xs text-white/65">
            <span>
              {product.stock_quantity} în stoc din {product.purchase_quantity} cumpărate
            </span>
            <span>Rată de vânzare {product.sell_through_rate}%</span>
            <span>ROI {product.roi}%</span>
          </div>
        </div>

        <div className="grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-2">
          {details.map(([label, value]) => (
            <div key={label} className="bg-background px-4 py-3.5">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                {label}
              </div>
              <div className="mt-1 font-mono text-sm font-semibold tabular-nums">{value}</div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function VatCard({ summaries }: { summaries: FinanceCurrencySummary[] }) {
  return (
    <Card className="reveal overflow-hidden" style={{ "--i": 7 } as CSSProperties}>
      <CardHeader className="border-b border-border/70 bg-muted/20 pb-4">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/15">
            <Landmark className="h-4 w-4" strokeWidth={1.5} />
          </span>
          <div>
            <CardTitle className="font-display text-base">Poziție TVA</CardTitle>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Doar pentru mișcările marcate explicit.
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-5">
        {summaries.map((summary, index) => (
          <div
            key={summary.currency}
            className={cn("space-y-4", index > 0 && "border-t border-border pt-5")}
          >
            {summaries.length > 1 ? (
              <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                {summary.currency}
              </div>
            ) : null}
            <VatRow label="TVA colectat" value={formatMoney(summary.sales_vat, summary.currency)} />
            <VatRow
              label="TVA recuperabil"
              value={formatMoney(summary.recoverable_vat, summary.currency)}
            />
            <div className="h-px bg-border" />
            <VatRow
              label={summary.vat_balance >= 0 ? "TVA estimat de plată" : "TVA estimat de recuperat"}
              value={formatMoney(Math.abs(summary.vat_balance), summary.currency)}
              strong
            />
          </div>
        ))}
        <p className="rounded-xl bg-muted/60 px-3 py-2.5 text-[10px] leading-relaxed text-muted-foreground">
          Este o estimare operațională, nu un document contabil. Regimul fiscal trebuie confirmat cu
          contabilul.
        </p>
      </CardContent>
    </Card>
  );
}

function VatRow({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span
        className={cn("text-xs text-muted-foreground", strong && "font-medium text-foreground")}
      >
        {label}
      </span>
      <span className={cn("font-mono text-sm tabular-nums", strong && "font-semibold")}>
        {value}
      </span>
    </div>
  );
}

function Ledger({
  transactions,
  onAdd,
  onDelete,
}: {
  transactions: FinanceTransaction[];
  onAdd: () => void;
  onDelete: (transaction: FinanceTransaction) => void;
}) {
  return (
    <Card className="reveal mt-6" style={{ "--i": 8 } as CSSProperties}>
      <CardHeader className="flex-row items-center justify-between border-b border-border/70 pb-4">
        <div>
          <CardTitle className="font-display text-base">Registru de mișcări</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Istoricul complet, fără suprascrierea prețurilor vechi.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onAdd}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Adaugă
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        {!transactions.length ? (
          <div className="grid min-h-48 place-items-center px-6 text-center">
            <div>
              <ReceiptText className="mx-auto h-6 w-6 text-muted-foreground" strokeWidth={1.5} />
              <p className="mt-3 text-sm font-medium">Nicio mișcare înregistrată</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Începe cu achiziția primului lot.
              </p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-border/70">
            {transactions.map((transaction) => {
              const meta = KIND_META[transaction.kind];
              const Icon = meta.icon;
              return (
                <div
                  key={`${transaction.account_id ?? ""}:${transaction.id}`}
                  className="group grid items-center gap-3 px-5 py-4 transition-colors hover:bg-muted/25 sm:grid-cols-[auto_minmax(0,1fr)_auto_auto]"
                >
                  <span className={cn("grid h-9 w-9 place-items-center rounded-xl", meta.tone)}>
                    <Icon className="h-4 w-4" strokeWidth={1.5} />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="text-sm font-semibold">{meta.label}</span>
                      <span className="truncate text-xs text-muted-foreground">
                        {transaction.product_title}
                      </span>
                      {transaction.account_label ? (
                        <AccountBadge account={{ display_name: transaction.account_label }} />
                      ) : null}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <CalendarDays className="h-3 w-3" />
                        {new Intl.DateTimeFormat("ro-RO", { dateStyle: "medium" }).format(
                          new Date(`${transaction.occurred_at}T12:00:00`),
                        )}
                      </span>
                      {transaction.kind !== "expense" ? (
                        <span>{transaction.quantity} buc.</span>
                      ) : null}
                      {transaction.vat_amount > 0 ? (
                        <span>TVA {formatMoney(transaction.vat_amount, transaction.currency)}</span>
                      ) : null}
                      {transaction.note ? (
                        <span className="truncate">{transaction.note}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="text-left sm:text-right">
                    <div className="font-mono text-sm font-semibold tabular-nums">
                      {transaction.kind === "sale" ? "+" : "−"}
                      {formatMoney(transaction.net_total, transaction.currency)}
                    </div>
                    <div className="mt-0.5 text-[10px] text-muted-foreground">
                      brut {formatMoney(transaction.gross_total, transaction.currency)}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="justify-self-end opacity-70 transition-opacity group-hover:opacity-100"
                    aria-label="Șterge mișcarea"
                    onClick={() => onDelete(transaction)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TransactionDialog({
  open,
  products,
  saving,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  products: ProductFinance[];
  saving: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (input: FinanceTransactionInput, accountId?: string) => void;
}) {
  const [draft, setDraft] = useState<FinanceTransactionInput>({
    product_id: "",
    kind: "purchase",
    quantity: 1,
    unit_price: 0,
    vat_rate: 21,
    vat_included: false,
    vat_deductible: false,
    occurred_at: localToday(),
    note: "",
  });

  const selected = useMemo(
    () => products.find((product) => product.product_id === draft.product_id),
    [draft.product_id, products],
  );

  // Dialogul nu se demonteaza la inchidere (doar se ascunde) — fara resetul
  // de mai jos, nota, data si cantitatea din ULTIMA inregistrare ramaneau in
  // formular la urmatoarea deschidere si puteau ajunge, neobservate, intr-o
  // miscare noua (alta data, alta nota). Se reseteaza complet doar la
  // TRANZITIA inchis->deschis, nu la fiecare refetch de produse cat timp
  // dialogul e deja deschis (ar sterge ce tocmai completa utilizatorul).
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open && !wasOpen.current && products.length) {
      const first = products[0];
      setDraft({
        product_id: first.product_id,
        kind: "purchase",
        quantity: 1,
        unit_price: 0,
        vat_rate: first.vat_rate || 21,
        vat_included: false,
        vat_deductible: false,
        occurred_at: localToday(),
        note: "",
      });
    }
    wasOpen.current = open;
  }, [open, products]);

  // Produsul selectat poate disparea in timp ce dialogul e deschis (rar —
  // ex. stergere din alt tab) — cadem pe primul produs disponibil, dar fara
  // sa atingem nota/data/cantitatea deja completate.
  useEffect(() => {
    if (!open || !products.length) return;
    const current = products.find((product) => product.product_id === draft.product_id);
    if (current) return;
    const first = products[0];
    setDraft((value) => ({
      ...value,
      product_id: first.product_id,
      unit_price: value.kind === "sale" ? first.sale_price : 0,
      vat_rate: first.vat_rate || 21,
      vat_included: value.kind === "sale" ? first.sale_vat_included : false,
      vat_deductible: false,
    }));
  }, [draft.product_id, open, products]);

  const chooseKind = (kind: FinanceTransactionKind) => {
    setDraft((value) => ({
      ...value,
      kind,
      quantity: kind === "expense" ? 1 : value.quantity,
      unit_price: kind === "sale" ? (selected?.sale_price ?? value.unit_price) : value.unit_price,
      vat_included: kind === "sale" ? (selected?.sale_vat_included ?? false) : false,
      vat_deductible: false,
    }));
  };

  const chooseProduct = (productId: string) => {
    const product = products.find((item) => item.product_id === productId);
    setDraft((value) => ({
      ...value,
      product_id: productId,
      unit_price: value.kind === "sale" ? (product?.sale_price ?? 0) : value.unit_price,
      vat_rate: product?.vat_rate || 21,
      vat_included:
        value.kind === "sale" ? (product?.sale_vat_included ?? false) : value.vat_included,
    }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    if (draft.quantity <= 0 || draft.unit_price < 0) {
      toast.error("Verifică prețul și cantitatea.");
      return;
    }
    onSubmit(draft, selected.account_id);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Înregistrează o mișcare</DialogTitle>
          <DialogDescription>
            Fiecare intrare rămâne în istoric și actualizează automat balanța produsului.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-5">
          <div className="grid grid-cols-3 gap-2 rounded-2xl bg-muted/70 p-1.5">
            {(Object.keys(KIND_META) as FinanceTransactionKind[]).map((kind) => {
              const meta = KIND_META[kind];
              const Icon = meta.icon;
              return (
                <button
                  key={kind}
                  type="button"
                  onClick={() => chooseKind(kind)}
                  className={cn(
                    "flex items-center justify-center gap-2 rounded-xl px-2 py-2.5 text-xs font-medium transition-all",
                    draft.kind === kind
                      ? "bg-card text-foreground shadow-sm ring-1 ring-border"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {meta.label}
                </button>
              );
            })}
          </div>

          <div>
            <Label htmlFor="finance-product">Produs</Label>
            <Select value={draft.product_id} onValueChange={chooseProduct}>
              <SelectTrigger id="finance-product" className="mt-2">
                <SelectValue placeholder="Alege produsul" />
              </SelectTrigger>
              <SelectContent>
                {products.map((product) => (
                  <SelectItem
                    key={`${product.account_id ?? ""}:${product.product_id}`}
                    value={product.product_id}
                  >
                    {product.title}
                    {product.account_label ? ` · ${product.account_label}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            {draft.kind !== "expense" ? (
              <div>
                <Label htmlFor="finance-quantity">Cantitate</Label>
                <Input
                  id="finance-quantity"
                  className="mt-2 font-mono"
                  type="number"
                  min={1}
                  step={1}
                  required
                  value={draft.quantity}
                  onChange={(event) =>
                    setDraft((value) => ({ ...value, quantity: Number(event.target.value) }))
                  }
                />
              </div>
            ) : null}
            <div className={cn(draft.kind === "expense" && "sm:col-span-2")}>
              <Label htmlFor="finance-price">
                {draft.kind === "expense" ? "Cost total" : "Preț unitar"}
              </Label>
              <div className="relative mt-2">
                <Input
                  id="finance-price"
                  className="pr-14 font-mono"
                  type="number"
                  min={0}
                  step="0.01"
                  required
                  value={draft.unit_price}
                  onChange={(event) =>
                    setDraft((value) => ({ ...value, unit_price: Number(event.target.value) }))
                  }
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] text-muted-foreground">
                  {selected?.currency ?? "RON"}
                </span>
              </div>
            </div>
            <div>
              <Label htmlFor="finance-date">Data</Label>
              <Input
                id="finance-date"
                className="mt-2 font-mono text-xs"
                type="date"
                required
                value={draft.occurred_at}
                onChange={(event) =>
                  setDraft((value) => ({ ...value, occurred_at: event.target.value }))
                }
              />
            </div>
          </div>

          <div className="rounded-2xl border border-border/80 bg-muted/25 p-4">
            <label className="flex cursor-pointer items-start gap-3">
              <Checkbox
                className="mt-0.5"
                checked={draft.vat_included}
                onCheckedChange={(checked) =>
                  setDraft((value) => ({
                    ...value,
                    vat_included: checked === true,
                    vat_deductible: checked === true ? value.vat_deductible : false,
                  }))
                }
              />
              <span>
                <span className="block text-sm font-medium">
                  {draft.kind === "sale" ? "Prețul include TVA de colectat" : "Prețul include TVA"}
                </span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  TVA-ul este separat din suma brută numai când această bifă este activă.
                </span>
              </span>
            </label>

            {draft.vat_included ? (
              <div className="mt-4 grid items-end gap-4 border-t border-border/70 pt-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="finance-vat-rate">Cotă TVA</Label>
                  <div className="relative mt-2">
                    <Input
                      id="finance-vat-rate"
                      className="pr-9 font-mono"
                      type="number"
                      min={0}
                      max={100}
                      step="0.01"
                      value={draft.vat_rate}
                      onChange={(event) =>
                        setDraft((value) => ({ ...value, vat_rate: Number(event.target.value) }))
                      }
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                      %
                    </span>
                  </div>
                </div>
                {draft.kind !== "sale" ? (
                  <label className="flex cursor-pointer items-center gap-3 rounded-xl bg-background px-3 py-2.5 ring-1 ring-border">
                    <Checkbox
                      checked={draft.vat_deductible}
                      onCheckedChange={(checked) =>
                        setDraft((value) => ({
                          ...value,
                          vat_deductible: checked === true,
                        }))
                      }
                    />
                    <span className="text-xs font-medium">TVA deductibil</span>
                  </label>
                ) : null}
              </div>
            ) : null}
          </div>

          <div>
            <Label htmlFor="finance-note">Notă opțională</Label>
            <Textarea
              id="finance-note"
              className="mt-2 min-h-20 resize-none"
              maxLength={500}
              placeholder={
                draft.kind === "expense"
                  ? "Ex.: transport, reparație, comision"
                  : "Ex.: furnizor, lot sau detalii utile"
              }
              value={draft.note}
              onChange={(event) => setDraft((value) => ({ ...value, note: event.target.value }))}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Renunță
            </Button>
            <Button type="submit" disabled={saving || !selected}>
              {saving ? "Se salvează…" : KIND_META[draft.kind].action}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function FinanceSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-5 lg:grid-cols-[1.15fr_1.85fr]">
        <Skeleton className="h-64 rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-32 rounded-2xl" />
          ))}
        </div>
      </div>
      <Skeleton className="h-80 rounded-2xl" />
    </div>
  );
}
