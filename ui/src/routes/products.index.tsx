import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pencil, Plus, Trash2, Package as PackageIcon } from "lucide-react";
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
import { deleteProduct, getProducts } from "@/lib/api";
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
  const productsQ = useQuery({ queryKey: ["products"], queryFn: getProducts });
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const del = useMutation({
    mutationFn: (id: string) => deleteProduct(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      toast.success("Produs șters");
      setPendingDelete(null);
    },
    onError: () => toast.error("Nu am putut șterge produsul"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Produse"
        description="Catalogul folosit de bot pentru a răspunde la întrebări."
        actions={
          <Button asChild>
            <Link to="/products/$productId" params={{ productId: "new" }}>
              <Plus className="mr-2 h-4 w-4" /> Adaugă produs
            </Link>
          </Button>
        }
      />

      {productsQ.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full" />
          ))}
        </div>
      ) : (productsQ.data ?? []).length === 0 ? (
        <EmptyState
          icon={<PackageIcon className="h-6 w-6" />}
          title="Niciun produs în catalog"
          description="Adaugă primul produs pentru ca botul să poată răspunde la întrebări."
          action={
            <Button asChild>
              <Link to="/products/$productId" params={{ productId: "new" }}>
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
              className="reveal hover-lift flex flex-col"
              style={{ "--i": 1 + i } as React.CSSProperties}
            >
              <CardContent className="flex flex-1 flex-col gap-4 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {p.category} · {p.subcategory}
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
                      <Link to="/products/$productId" params={{ productId: p.id }}>
                        <Pencil className="mr-1.5 h-3.5 w-3.5" /> Editează
                      </Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setPendingDelete(p.id)}
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

      <AlertDialog
        open={!!pendingDelete}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ștergi acest produs?</AlertDialogTitle>
            <AlertDialogDescription>
              Acțiunea este definitivă. Botul nu va mai putea răspunde la întrebări
              despre acest produs.
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
    </AppShell>
  );
}