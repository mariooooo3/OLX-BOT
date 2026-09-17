import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  Copy,
  Pencil,
  Plus,
  Trash2,
  Package as PackageIcon,
  DownloadCloud,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
import { EmptyState } from "@/components/empty-state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  copyProduct,
  deleteProduct,
  getActiveListings,
  getProducts,
  saveProduct,
  type OlxAccount,
} from "@/lib/api";
import { AccountBadge, accountBorderClass, scopeLabel } from "@/components/account-scope";
import { SellerInfoCard } from "@/components/seller-info-card";
import { ALL_ACCOUNTS, useAccountScope, useAccounts, findAccount } from "@/lib/accounts";
import { accountDisplayName } from "@/components/account-menu";
import type { ActiveListing, Product } from "@/lib/types";
import { formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/products/")({
  head: () => ({
    meta: [
      { title: "Produse — OLX Bot" },
      { name: "description", content: "Catalog produse gestionate de botul OLX." },
    ],
  }),
  component: ProductsPage,
});

function ProductsPage() {
  const qc = useQueryClient();
  // acelasi scope ca in Dashboard/Conversatii — catalogul urmeaza contul ales
  const [scope] = useAccountScope();
  const { accounts } = useAccounts();
  const productsQ = useQuery({
    queryKey: ["products", scope],
    queryFn: () => getProducts(scope === ALL_ACCOUNTS ? undefined : scope),
  });
  const [pendingDelete, setPendingDelete] = useState<Product | null>(null);
  const [copySource, setCopySource] = useState<Product | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const scopeName = scopeLabel(scope, accounts);

  // produsul nou se creeaza pe contul din scope; pe "toate conturile" cade pe
  // contul selectat in meniu, fiindca un catalog are nevoie de un proprietar
  const newProductAccount = scope === ALL_ACCOUNTS ? undefined : scope;

  const del = useMutation({
    mutationFn: (p: Product) => deleteProduct(p.id, p.account_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      toast.success("Produs șters");
      setPendingDelete(null);
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Nu am putut șterge produsul"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Produse"
        description="Catalogul folosit de bot pentru a răspunde la întrebări."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setImportOpen(true)}>
              <DownloadCloud className="mr-2 h-4 w-4" /> Importă din OLX
            </Button>
            <Button asChild>
              <Link
                to="/products/$productId"
                params={{ productId: "new" }}
                search={{ account: newProductAccount }}
              >
                <Plus className="mr-2 h-4 w-4" /> Adaugă produs
              </Link>
            </Button>
          </div>
        }
      />

      {/* informatiile generale stau deasupra catalogului: se aplica tuturor
          anunturilor, nu unui produs anume */}
      <SellerInfoCard />

      {productsQ.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full" />
          ))}
        </div>
      ) : (productsQ.data ?? []).length === 0 ? (
        <EmptyState
          icon={<PackageIcon className="h-6 w-6" />}
          title={scopeName ? `Niciun produs pe contul ${scopeName}` : "Niciun produs în catalog"}
          description={
            scopeName
              ? `Catalogul contului ${scopeName} e gol. Adaugă un produs sau copiază unul de pe alt cont.`
              : "Adaugă primul produs pentru ca botul să poată răspunde la întrebări."
          }
          action={
            <Button asChild>
              <Link
                to="/products/$productId"
                params={{ productId: "new" }}
                search={{ account: newProductAccount }}
              >
                <Plus className="mr-2 h-4 w-4" /> Adaugă produs
              </Link>
            </Button>
          }
        />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {(productsQ.data ?? []).map((p, i) => (
            <Card
              key={p.id}
              className={cn(
                "reveal hover-lift flex flex-col",
                // bara colorata = contul in al carui catalog e produsul
                accountBorderClass(findAccount(accounts, p.account_id)?.color),
              )}
              style={{ "--i": 1 + i } as React.CSSProperties}
            >
              <CardContent className="flex flex-1 flex-col gap-4 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <AccountBadge
                      className="mb-1.5"
                      account={{
                        display_name: p.account_label,
                        color: findAccount(accounts, p.account_id)?.color,
                      }}
                    />
                    <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {p.negotiable ? "Preț negociabil" : "Preț fix"}
                    </div>
                    <h3 className="mt-1 line-clamp-2 text-sm font-semibold leading-snug">
                      {p.title}
                    </h3>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
                      p.condition === "nou"
                        ? "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-500/25"
                        : "bg-blue-50 text-blue-700 ring-blue-200 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-500/25",
                    )}
                  >
                    {p.condition === "nou" ? "Nou" : "Folosit"}
                  </span>
                </div>

                <div className="mt-auto flex items-end justify-between">
                  <div>
                    <div className="font-mono text-lg font-semibold tracking-tight tabular-nums">
                      {formatPrice(p.price, p.currency)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Stoc: <span className="font-mono">{p.stock}</span>{" "}
                      {p.stock === 1 ? "bucată" : "bucăți"}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" asChild>
                      <Link
                        to="/products/$productId"
                        params={{ productId: p.id }}
                        search={{ account: undefined }}
                      >
                        <Pencil className="mr-1.5 h-3.5 w-3.5" /> Editează
                      </Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCopySource(p)}
                      aria-label="Copiază produsul pe alt cont"
                      title="Copiază pe alt cont"
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setPendingDelete(p)}
                      aria-label="Șterge produs"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <AlertDialog open={!!pendingDelete} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ștergi acest produs?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.account_label
                ? `Se șterge „${pendingDelete.title}” din catalogul contului ${pendingDelete.account_label}. Copiile de pe alte conturi rămân neatinse. `
                : ""}
              Acțiunea este definitivă. Botul nu va mai putea răspunde la întrebări despre acest
              produs.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Anulează</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => pendingDelete && del.mutate(pendingDelete)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Șterge
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <CopyProductDialog
        product={copySource}
        accounts={accounts}
        onClose={() => setCopySource(null)}
        onCopied={() => qc.invalidateQueries({ queryKey: ["products"] })}
      />

      <ImportListingsDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        accounts={accounts}
        defaultAccountId={scope === ALL_ACCOUNTS ? undefined : scope}
        onImported={() => qc.invalidateQueries({ queryKey: ["products"] })}
      />
    </AppShell>
  );
}

/**
 * Copierea unui produs pe alte conturi.
 *
 * Copiile sunt produse independente: dupa copiere le editezi separat pe
 * fiecare cont (preturile si stocul difera de obicei de la un cont la altul).
 */
function CopyProductDialog({
  product,
  accounts,
  onClose,
  onCopied,
}: {
  product: Product | null;
  accounts: OlxAccount[];
  onClose: () => void;
  onCopied: () => void;
}) {
  const [targets, setTargets] = useState<string[]>([]);
  const others = accounts.filter((a) => a.id !== product?.account_id);

  const copy = useMutation({
    mutationFn: () => copyProduct(product!.id, targets),
    onSuccess: ({ count }) => {
      onCopied();
      onClose();
      setTargets([]);
      toast.success(count === 1 ? "Produs copiat pe 1 cont" : `Produs copiat pe ${count} conturi`);
    },
    onError: () => toast.error("Nu am putut copia produsul"),
  });

  const toggle = (id: string) =>
    setTargets((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );

  return (
    <Dialog
      open={!!product}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
          setTargets([]);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Copiază „{product?.title}"</DialogTitle>
          <DialogDescription>
            Alege conturile pe care vrei o copie. Copiile sunt independente: le poți edita separat,
            cu prețuri și stocuri diferite.
          </DialogDescription>
        </DialogHeader>

        {others.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nu ai alt cont pe care să copiezi produsul.
          </p>
        ) : (
          <div className="space-y-1">
            {others.map((a) => (
              <label
                key={a.id}
                className="flex cursor-pointer items-center gap-3 rounded-xl px-2 py-2 hover:bg-muted/50"
              >
                <Checkbox checked={targets.includes(a.id)} onCheckedChange={() => toggle(a.id)} />
                <AccountBadge account={{ display_name: accountDisplayName(a), color: a.color }} />
                {!a.connected ? (
                  <span className="text-[10px] text-muted-foreground">neconectat</span>
                ) : null}
              </label>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Renunță
          </Button>
          <Button disabled={targets.length === 0 || copy.isPending} onClick={() => copy.mutate()}>
            {copy.isPending
              ? "Se copiază…"
              : `Copiază pe ${targets.length} ${targets.length === 1 ? "cont" : "conturi"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Import produse din anunturile ACTIVE ale unui cont OLX conectat.
 *
 * Nu se salveaza nimic automat: userul alege contul, apasa "Extrage",
 * bifeaza ce vrea, apoi "Importa". Titlul si pretul se completeaza direct
 * din anunt; restul (stare, garantie, TVA, FAQ) ramane de completat manual
 * dupa, exact ca la un produs adaugat de mana — extractia nu poate ghici
 * campurile alea.
 */
function ImportListingsDialog({
  open,
  onClose,
  accounts,
  defaultAccountId,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  accounts: OlxAccount[];
  defaultAccountId?: string;
  onImported: () => void;
}) {
  const connected = accounts.filter((a) => a.connected);
  const [accountId, setAccountId] = useState<string | undefined>(defaultAccountId);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // `accounts` se incarca async (query separat) — la montarea paginii poate
  // fi inca goala, deci alegerea implicita nu se poate face o singura data
  // in useState (ar ramane goala pentru totdeauna). Recalculam de fiecare
  // data cand dialogul se deschide sau lista de conturi conectate se
  // schimba, dar NU stricam o alegere deja valida a userului.
  const connectedIds = connected.map((a) => a.id).join(",");
  useEffect(() => {
    if (!open) return;
    setAccountId((current) => {
      if (current && connected.some((a) => a.id === current)) return current;
      if (defaultAccountId && connected.some((a) => a.id === defaultAccountId)) {
        return defaultAccountId;
      }
      return connected[0]?.id;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, connectedIds, defaultAccountId]);

  const extract = useMutation({
    mutationFn: (id: string) => getActiveListings(id),
    onSuccess: (data) => {
      // implicit toate bifate — cazul comun e sa le vrei pe toate
      setSelected(new Set(data.listings.map((l) => l.url)));
      if (data.listings.length === 0) {
        toast.info("Niciun anunț activ găsit pe acest cont.");
      }
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Nu am putut extrage anunțurile"),
  });

  const toggle = (url: string) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });

  const importSelected = useMutation({
    mutationFn: async () => {
      const items = (extract.data?.listings ?? []).filter((l) => selected.has(l.url));
      let count = 0;
      for (const item of items) {
        await saveProduct(productFromListing(item), accountId);
        count += 1;
      }
      return count;
    },
    onSuccess: (count) => {
      onImported();
      toast.success(count === 1 ? "1 produs importat" : `${count} produse importate`);
      handleClose();
    },
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "Importul a eșuat la un produs"),
  });

  function handleClose() {
    setSelected(new Set());
    extract.reset();
    onClose();
  }

  const listings = extract.data?.listings ?? [];

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Importă din OLX</DialogTitle>
          <DialogDescription>
            Extrage anunțurile active ale unui cont conectat și alege ce adaugi în catalog. Titlul
            și prețul se completează automat — restul (stare, garanție, FAQ) rămâne de completat
            manual, ca la orice produs adăugat direct.
          </DialogDescription>
        </DialogHeader>

        {connected.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Niciun cont conectat momentan — conectează unul din panoul de conturi.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Select
                value={accountId}
                onValueChange={(value) => {
                  setAccountId(value);
                  extract.reset();
                  setSelected(new Set());
                }}
              >
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Alege contul" />
                </SelectTrigger>
                <SelectContent>
                  {connected.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {accountDisplayName(a)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                disabled={!accountId || extract.isPending}
                onClick={() => accountId && extract.mutate(accountId)}
              >
                {extract.isPending ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.5} />
                ) : (
                  <RefreshCw className="mr-1.5 h-4 w-4" strokeWidth={1.5} />
                )}
                Extrage
              </Button>
            </div>

            {extract.isPending ? (
              <p className="text-xs text-muted-foreground">
                Citesc anunțurile active de pe OLX — poate dura până la un minut.
              </p>
            ) : listings.length > 0 ? (
              <ul className="max-h-72 space-y-1.5 overflow-y-auto">
                {listings.map((item) => (
                  <li key={item.url}>
                    <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border/70 bg-muted/30 px-2.5 py-2 text-xs transition-colors hover:bg-muted/50">
                      <Checkbox
                        className="mt-0.5"
                        checked={selected.has(item.url)}
                        onCheckedChange={() => toggle(item.url)}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{item.title}</span>
                        <span className="text-muted-foreground">
                          {item.price !== null && item.currency
                            ? formatPrice(item.price, item.currency)
                            : (item.price_text ?? "preț nespecificat")}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={handleClose}>
            Renunță
          </Button>
          <Button
            disabled={selected.size === 0 || importSelected.isPending}
            onClick={() => importSelected.mutate()}
          >
            {importSelected.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.5} />
            ) : null}
            Importă{selected.size > 0 ? ` (${selected.size})` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Produsul nou, cu campurile stiute din anunt; restul ia valorile implicite
 *  (identice cu core/product_schema.py:empty_product(), ca sa nu difere de
 *  ce ai obtine adaugand manual acelasi produs). */
function productFromListing(item: ActiveListing): Product {
  return {
    id: "",
    title: item.title,
    price: item.price ?? 0,
    currency: item.currency ?? "RON",
    stock: 1,
    condition: "folosit",
    negotiable: false,
    warranty: "",
    vat: { included: true, deductible: false, rate: 21 },
    about: `Importat de pe OLX: ${item.url}`,
    faq: [],
  };
}
