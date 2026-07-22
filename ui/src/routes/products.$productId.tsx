import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
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
  component: ProductEditPage,
});

const emptyProduct = (): Product => ({
  id: "",
  title: "",
  price: 0,
  currency: "RON",
  stock: 1,
  condition: "folosit",
  negotiable: false,
  warranty: "",
  vat: { included: true, deductible: false, rate: 21 },
  about: "",
  faq: [],
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

  useEffect(() => {
    if (isNew) {
      setForm(emptyProduct());
      return;
    }
    // produsele vechi pot avea campuri lipsa — completam cu valorile implicite
    if (q.data) setForm({ ...emptyProduct(), ...q.data });
  }, [q.data, isNew]);

  const save = useMutation({
    mutationFn: () =>
      // la creare trimitem contul tinta; la editare il lasam pe server sa
      // pastreze contul proprietar, ca produsul sa nu migreze intre conturi
      saveProduct(form, isNew ? targetAccount : undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["product", productId] });
      toast.success(isNew ? "Produs adăugat" : "Modificări salvate");
      navigate({ to: "/products" });
    },
    onError: () => toast.error("Nu am putut salva produsul"),
  });

  const set = <K extends keyof Product>(key: K, value: Product[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const setFaq = (index: number, field: "question" | "answer", value: string) =>
    setForm((f) => {
      const faq = [...f.faq];
      faq[index] = { ...faq[index], [field]: value };
      return { ...f, faq };
    });

  if (!isNew && q.isLoading) {
    return (
      <AppShell>
        <Skeleton className="h-96 w-full" />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title={isNew ? "Produs nou" : form.title || "Editează produsul"}
        description="Botul răspunde exact din câmpurile de mai jos."
        actions={
          <Button variant="outline" onClick={() => navigate({ to: "/products" })}>
            <ArrowLeft className="mr-2 h-4 w-4" /> Înapoi
          </Button>
        }
      />

      <form
        className="grid max-w-3xl gap-6"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Date de bază</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor="title">Titlu</Label>
              <p className="mb-1.5 text-xs text-muted-foreground">
                Trebuie să fie același cu titlul anunțului de pe OLX — după el recunoaște botul
                despre ce produs e conversația.
              </p>
              <Input
                id="title"
                value={form.title}
                onChange={(e) => set("title", e.target.value)}
                required
              />
            </div>

            <div>
              <Label htmlFor="price">Preț</Label>
              <Input
                id="price"
                type="number"
                min={0}
                value={form.price}
                onChange={(e) => set("price", Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="currency">Monedă</Label>
              <Input
                id="currency"
                value={form.currency}
                onChange={(e) => set("currency", e.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="stock">Stoc</Label>
              <Input
                id="stock"
                type="number"
                min={0}
                value={form.stock}
                onChange={(e) => set("stock", Number(e.target.value))}
              />
            </div>
            <div>
              <Label>Stare</Label>
              <Select
                value={form.condition}
                onValueChange={(v) => set("condition", v as Product["condition"])}
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

            <div className="flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-muted/30 px-3 py-2.5 sm:col-span-2">
              <div>
                <Label className="cursor-pointer">Prețul e negociabil</Label>
                <p className="text-xs text-muted-foreground">
                  Cea mai frecventă întrebare de pe OLX — răspunsul va fi exact.
                </p>
              </div>
              <Switch checked={form.negotiable} onCheckedChange={(v) => set("negotiable", v)} />
            </div>

            <div className="sm:col-span-2">
              <Label htmlFor="warranty">Garanție</Label>
              <Input
                id="warranty"
                placeholder='ex. "12 luni" sau "fără"'
                value={form.warranty}
                onChange={(e) => set("warranty", e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">TVA și facturare</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex items-center justify-between gap-3">
              <Label className="cursor-pointer">Prețul afișat include TVA</Label>
              <Switch
                checked={form.vat.included}
                onCheckedChange={(v) => set("vat", { ...form.vat, included: v })}
              />
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label className="cursor-pointer">Se emite factură, TVA deductibil</Label>
                <p className="text-xs text-muted-foreground">Pentru cumpărători firmă.</p>
              </div>
              <Switch
                checked={form.vat.deductible}
                onCheckedChange={(v) => set("vat", { ...form.vat, deductible: v })}
              />
            </div>
            <div className="max-w-[160px]">
              <Label htmlFor="vat-rate">Cotă TVA (%)</Label>
              <Input
                id="vat-rate"
                type="number"
                min={0}
                max={100}
                value={form.vat.rate}
                onChange={(e) => set("vat", { ...form.vat, rate: Number(e.target.value) })}
              />
            </div>
            {!form.vat.included && form.price > 0 ? (
              <p className="rounded-lg bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                Botul va spune: preț fără TVA {form.price} {form.currency}, cu TVA{" "}
                <strong className="text-foreground">
                  {(form.price * (1 + form.vat.rate / 100)).toFixed(2)} {form.currency}
                </strong>{" "}
                — sumă calculată, nu compusă de model.
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Despre produs</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-2 text-xs text-muted-foreground">
              Scrie liber, ca într-un anunț: specificații, culoare, ce include, stare. De aici
              răspunde botul la întrebările care nu sunt acoperite mai sus.
            </p>
            <Textarea
              rows={7}
              value={form.about}
              onChange={(e) => set("about", e.target.value)}
              placeholder="ex. Aer condiționat 12000 BTU, culoare albă, folosit un sezon, include telecomandă și kit de montaj."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Întrebări frecvente</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Opțional. Când întrebarea cumpărătorului se potrivește clar, răspunsul tău se trimite{" "}
              <strong>cuvânt cu cuvânt</strong>. Toate intră oricum în contextul botului, deci nu se
              pot pierde.
            </p>
            {form.faq.map((f, i) => (
              <div key={i} className="space-y-2 rounded-xl border border-border/70 p-3">
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Întrebarea"
                    value={f.question}
                    onChange={(e) => setFaq(i, "question", e.target.value)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label="Șterge întrebarea"
                    onClick={() =>
                      set(
                        "faq",
                        form.faq.filter((_, idx) => idx !== i),
                      )
                    }
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
                <Textarea
                  rows={2}
                  placeholder="Răspunsul tău, exact cum vrei să fie trimis"
                  value={f.answer}
                  onChange={(e) => setFaq(i, "answer", e.target.value)}
                />
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => set("faq", [...form.faq, { question: "", answer: "" }])}
            >
              <Plus className="mr-2 h-4 w-4" /> Adaugă întrebare
            </Button>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button variant="outline" type="button" onClick={() => navigate({ to: "/products" })}>
            Renunță
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Se salvează…" : "Salvează produsul"}
          </Button>
        </div>
      </form>
    </AppShell>
  );
}
