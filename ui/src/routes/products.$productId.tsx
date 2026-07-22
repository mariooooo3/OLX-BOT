import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type KeyboardEvent } from "react";
import { ArrowLeft, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getProduct, saveProduct } from "@/lib/api";
import type { Product } from "@/lib/types";

export const Route = createFileRoute("/products/$productId")({
  // contul pe care se creeaza produsul nou (vine din scope-ul paginii Produse);
  // la editare nu conteaza — serverul pastreaza contul care detine produsul
  validateSearch: (search: Record<string, unknown>) => ({
    account: typeof search.account === "string" ? search.account : undefined,
  }),
  head: () => ({
    meta: [{ title: "Editare produs — OLX Bot" }],
  }),
  component: ProductEditPage,
});

const emptyProduct = (): Product => ({
  id: "",
  title: "",
  category: "",
  subcategory: "",
  price: 0,
  currency: "RON",
  stock: 1,
  condition: "folosit",
  description: "",
  attributes: {},
  faq: [],
  shipping: { available: false, courier: null, cost_paid_by: null, estimated_days: null },
  keywords: [],
});

function ProductEditPage() {
  const { productId } = Route.useParams();
  const { account: targetAccount } = Route.useSearch();
  const isNew = productId === "new";
  const navigate = useNavigate();
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["product", productId],
    queryFn: () => getProduct(productId),
    enabled: !isNew,
  });

  const [form, setForm] = useState<Product>(emptyProduct());
  const [attrs, setAttrs] = useState<Array<[string, string]>>([]);
  const [keywordInput, setKeywordInput] = useState("");

  useEffect(() => {
    if (isNew) {
      setForm(emptyProduct());
      setAttrs([]);
      return;
    }
    if (q.data) {
      setForm(q.data);
      setAttrs(Object.entries(q.data.attributes));
    }
  }, [q.data, isNew]);

  const save = useMutation({
    mutationFn: async () => {
      const attributes: Record<string, string> = {};
      for (const [k, v] of attrs) if (k.trim()) attributes[k.trim()] = v;
      const payload: Product = { ...form, attributes };
      // la creare trimitem contul tinta; la editare il lasam pe server sa
      // pastreze contul proprietar, ca produsul sa nu migreze intre conturi
      return saveProduct(payload, isNew ? targetAccount : undefined);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["product", productId] });
      toast.success(isNew ? "Produs adăugat" : "Modificări salvate");
      navigate({ to: "/products" });
    },
    onError: () => toast.error("Nu am putut salva produsul"),
  });

  if (!isNew && q.isLoading) {
    return (
      <AppShell>
        <PageHeader title="Se încarcă…" />
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </AppShell>
    );
  }

  const addKeyword = (k: string) => {
    const v = k.trim();
    if (!v || form.keywords.includes(v)) return;
    setForm({ ...form, keywords: [...form.keywords, v] });
  };
  const removeKeyword = (k: string) =>
    setForm({ ...form, keywords: form.keywords.filter((x) => x !== k) });

  const onKeywordKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addKeyword(keywordInput);
      setKeywordInput("");
    } else if (e.key === "Backspace" && !keywordInput && form.keywords.length) {
      setForm({ ...form, keywords: form.keywords.slice(0, -1) });
    }
  };

  return (
    <AppShell>
      <PageHeader
        title={isNew ? "Adaugă produs" : "Editează produs"}
        description={isNew ? "Completează detaliile pentru un produs nou." : form.title}
        actions={
          <Button variant="outline" asChild>
            <Link to="/products">
              <ArrowLeft className="mr-2 h-4 w-4" /> Înapoi
            </Link>
          </Button>
        }
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
        className="space-y-4"
      >
        {/* Date generale */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Date generale</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor="title">Titlu</Label>
              <Input
                id="title"
                required
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                Folosește exact titlul anunțului de pe OLX — botul asociază automat conversațiile cu
                produsul după titlu.
              </p>
            </div>
            <div>
              <Label htmlFor="category">Categorie</Label>
              <Input
                id="category"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="subcategory">Subcategorie</Label>
              <Input
                id="subcategory"
                value={form.subcategory}
                onChange={(e) => setForm({ ...form, subcategory: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="price">Preț</Label>
              <Input
                id="price"
                type="number"
                min={0}
                value={form.price}
                onChange={(e) => setForm({ ...form, price: Number(e.target.value) })}
              />
            </div>
            <div>
              <Label htmlFor="currency">Monedă</Label>
              <Input
                id="currency"
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="stock">Stoc</Label>
              <Input
                id="stock"
                type="number"
                min={0}
                value={form.stock}
                onChange={(e) => setForm({ ...form, stock: Number(e.target.value) })}
              />
            </div>
            <div>
              <Label>Condiție</Label>
              <Select
                value={form.condition}
                onValueChange={(v) => setForm({ ...form, condition: v as Product["condition"] })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="nou">Nou</SelectItem>
                  <SelectItem value="folosit">Folosit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="description">Descriere</Label>
              <Textarea
                id="description"
                rows={4}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
          </CardContent>
        </Card>

        {/* Atribute */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Atribute</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setAttrs([...attrs, ["", ""]])}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" /> Adaugă
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {attrs.length === 0 ? (
              <p className="text-sm text-muted-foreground">Niciun atribut definit.</p>
            ) : (
              attrs.map(([k, v], idx) => (
                <div key={idx} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                  <Input
                    placeholder="Cheie (ex: Culoare)"
                    value={k}
                    onChange={(e) => {
                      const next = [...attrs];
                      next[idx] = [e.target.value, v];
                      setAttrs(next);
                    }}
                  />
                  <Input
                    placeholder="Valoare (ex: Negru)"
                    value={v}
                    onChange={(e) => {
                      const next = [...attrs];
                      next[idx] = [k, e.target.value];
                      setAttrs(next);
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => setAttrs(attrs.filter((_, i) => i !== idx))}
                    aria-label="Șterge atribut"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* FAQ */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Întrebări frecvente</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setForm({ ...form, faq: [...form.faq, { question: "", answer: "" }] })}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" /> Adaugă
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {form.faq.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nicio întrebare definită.</p>
            ) : (
              form.faq.map((item, idx) => (
                <div key={idx} className="grid gap-2 rounded-md border border-border p-3">
                  <div className="flex items-start gap-2">
                    <Input
                      placeholder="Întrebare"
                      value={item.question}
                      onChange={(e) => {
                        const next = [...form.faq];
                        next[idx] = { ...next[idx], question: e.target.value };
                        setForm({ ...form, faq: next });
                      }}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        setForm({ ...form, faq: form.faq.filter((_, i) => i !== idx) })
                      }
                      aria-label="Șterge întrebare"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                  <Textarea
                    placeholder="Răspuns"
                    rows={2}
                    value={item.answer}
                    onChange={(e) => {
                      const next = [...form.faq];
                      next[idx] = { ...next[idx], answer: e.target.value };
                      setForm({ ...form, faq: next });
                    }}
                  />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Livrare */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Livrare</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <Label htmlFor="shipping">Livrare disponibilă</Label>
              <Switch
                id="shipping"
                checked={form.shipping.available}
                onCheckedChange={(v) =>
                  setForm({
                    ...form,
                    shipping: v
                      ? {
                          available: true,
                          courier: form.shipping.courier ?? "",
                          cost_paid_by: form.shipping.cost_paid_by ?? "buyer",
                          estimated_days: form.shipping.estimated_days ?? 2,
                        }
                      : {
                          available: false,
                          courier: null,
                          cost_paid_by: null,
                          estimated_days: null,
                        },
                  })
                }
              />
            </div>
            {form.shipping.available ? (
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <Label htmlFor="courier">Curier</Label>
                  <Input
                    id="courier"
                    value={form.shipping.courier ?? ""}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        shipping: { ...form.shipping, courier: e.target.value },
                      })
                    }
                  />
                </div>
                <div>
                  <Label>Plătit de</Label>
                  <Select
                    value={form.shipping.cost_paid_by ?? "buyer"}
                    onValueChange={(v) =>
                      setForm({
                        ...form,
                        shipping: {
                          ...form.shipping,
                          cost_paid_by: v as "buyer" | "seller",
                        },
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="buyer">Cumpărător</SelectItem>
                      <SelectItem value="seller">Vânzător</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="days">Zile estimate</Label>
                  <Input
                    id="days"
                    type="number"
                    min={1}
                    value={form.shipping.estimated_days ?? 0}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        shipping: {
                          ...form.shipping,
                          estimated_days: Number(e.target.value),
                        },
                      })
                    }
                  />
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Keywords */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cuvinte cheie</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2 rounded-md border border-input bg-background p-2 focus-within:ring-2 focus-within:ring-ring">
              {form.keywords.map((k) => (
                <span
                  key={k}
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs font-medium text-accent-foreground"
                >
                  {k}
                  <button
                    type="button"
                    onClick={() => removeKeyword(k)}
                    className="opacity-70 hover:opacity-100"
                    aria-label={`Șterge ${k}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
              <input
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={onKeywordKey}
                placeholder={form.keywords.length === 0 ? "Adaugă cuvinte cheie (Enter)" : ""}
                className="flex-1 min-w-[120px] bg-transparent px-1 py-1 text-sm outline-none"
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Apasă Enter sau virgulă pentru a adăuga.
            </p>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" asChild>
            <Link to="/products">Anulează</Link>
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Se salvează…" : "Salvează"}
          </Button>
        </div>
      </form>
    </AppShell>
  );
}
