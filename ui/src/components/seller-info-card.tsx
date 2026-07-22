/**
 * Informatiile generale ale vanzatorului: oras, livrare, plata.
 *
 * Stau langa produse, nu in Setari: sunt date despre ce vinzi, nu configurare
 * tehnica a botului. Se completeaza o data per cont si se aplica tuturor
 * anunturilor — inclusiv cand niciun produs din catalog nu se potriveste cu
 * anuntul, caz in care altfel botul ar raspunde generic.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Store } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getSettings, saveSettings } from "@/lib/api";
import { ALL_ACCOUNTS, useAccountScope, useAccounts } from "@/lib/accounts";
import { scopeLabel } from "@/components/account-scope";
import type { SellerInfo } from "@/lib/types";

const EMPTY: SellerInfo = {
  city: "",
  pickup_available: true,
  delivery_available: false,
  courier: "",
  delivery_paid_by: "buyer",
  payment_methods: "",
};

export function SellerInfoCard() {
  const qc = useQueryClient();
  const [scope] = useAccountScope();
  const { accounts } = useAccounts();
  const scopeName = scopeLabel(scope, accounts);

  const q = useQuery({
    queryKey: ["settings", scope],
    queryFn: () => getSettings(scope === ALL_ACCOUNTS ? undefined : scope),
  });

  const [form, setForm] = useState<SellerInfo>(EMPTY);
  const [loaded, setLoaded] = useState<SellerInfo>(EMPTY);

  useEffect(() => {
    if (!q.data) return;
    const info = { ...EMPTY, ...(q.data.seller_info ?? {}) };
    setForm(info);
    setLoaded(info);
  }, [q.data]);

  const dirty = JSON.stringify(form) !== JSON.stringify(loaded);

  const save = useMutation({
    // trimitem doar seller_info: restul setarilor contului raman neatinse
    mutationFn: () => saveSettings({ seller_info: form }, scope === ALL_ACCOUNTS ? "all" : scope),
    onSuccess: () => {
      setLoaded(form);
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success(
        scope === ALL_ACCOUNTS
          ? `Informații salvate pe ${accounts.length} conturi`
          : `Informații salvate pe contul ${scopeName}`,
      );
    },
    onError: () => toast.error("Nu am putut salva informațiile"),
  });

  const set = <K extends keyof SellerInfo>(key: K, value: SellerInfo[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <Card className="reveal mb-6" style={{ "--i": 0 } as React.CSSProperties}>
      <CardContent className="p-5">
        <div className="mb-4 flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground">
            <Store className="h-4 w-4" strokeWidth={1.5} />
          </span>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold">Informații generale</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Valabile pentru toate anunțurile
              {scopeName ? ` contului ${scopeName}` : " conturilor"}. Botul răspunde din ele chiar
              și când întrebarea nu e despre un produs anume.
            </p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="seller-city">Oraș</Label>
            <Input
              id="seller-city"
              placeholder="ex. Iași"
              value={form.city}
              onChange={(e) => set("city", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="seller-payment">Metode de plată</Label>
            <Input
              id="seller-payment"
              placeholder="ex. numerar la ridicare, transfer bancar"
              value={form.payment_methods}
              onChange={(e) => set("payment_methods", e.target.value)}
            />
          </div>

          <div className="flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-muted/30 px-3 py-2.5">
            <Label className="cursor-pointer text-sm">Se poate ridica personal</Label>
            <Switch
              checked={form.pickup_available}
              onCheckedChange={(v) => set("pickup_available", v)}
            />
          </div>
          <div className="flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-muted/30 px-3 py-2.5">
            <Label className="cursor-pointer text-sm">Trimit prin curier</Label>
            <Switch
              checked={form.delivery_available}
              onCheckedChange={(v) => set("delivery_available", v)}
            />
          </div>

          {form.delivery_available ? (
            <>
              <div>
                <Label htmlFor="seller-courier">Curier</Label>
                <Input
                  id="seller-courier"
                  placeholder="ex. FanCourier"
                  value={form.courier}
                  onChange={(e) => set("courier", e.target.value)}
                />
              </div>
              <div>
                <Label>Transportul e plătit de</Label>
                <Select
                  value={form.delivery_paid_by}
                  onValueChange={(v) =>
                    set("delivery_paid_by", v as SellerInfo["delivery_paid_by"])
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
            </>
          ) : null}
        </div>

        {dirty ? (
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setForm(loaded)}>
              Renunță
            </Button>
            <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Se salvează…" : "Salvează informațiile"}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
