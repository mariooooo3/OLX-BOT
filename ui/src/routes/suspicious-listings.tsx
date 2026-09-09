import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Check, Clipboard, ExternalLink, Flag, Plus, SearchCheck, Settings2, ShieldAlert, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/empty-state";
import {
  addSuspiciousListing,
  deleteSuspiciousListing,
  getSuspiciousListings,
  saveSuspiciousRules,
  saveSuspiciousListingMessage,
  setSuspiciousListingStatus,
} from "@/lib/api";
import { ALL_ACCOUNTS, useAccountScope } from "@/lib/accounts";
import { formatPrice } from "@/lib/format";
import type { SuspiciousListing, SuspiciousRules } from "@/lib/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/suspicious-listings")({
  head: () => ({ meta: [{ title: "Verificări anunțuri — OLX Bot" }] }),
  component: SuspiciousListingsPage,
});

const EMPTY_LISTING = { title: "", url: "", price: null as number | null, currency: "RON", description: "" };

function SuspiciousListingsPage() {
  const qc = useQueryClient();
  const [scope] = useAccountScope();
  // Regulile sunt per cont; în modul „toate” folosim contul activ, ca să nu
  // răspândim din greșeală o regulă diferită peste toate conturile.
  const accountId = scope === ALL_ACCOUNTS ? undefined : scope;
  const query = useQuery({ queryKey: ["suspiciousListings", accountId], queryFn: () => getSuspiciousListings(accountId) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["suspiciousListings"] });

  const saveRules = useMutation({ mutationFn: (rules: SuspiciousRules) => saveSuspiciousRules(rules, accountId), onSuccess: () => { refresh(); toast.success("Regulile au fost actualizate"); }, onError: showError });
  const add = useMutation({ mutationFn: (listing: typeof EMPTY_LISTING) => addSuspiciousListing(listing, accountId), onSuccess: () => { refresh(); toast.success("Anunț analizat"); }, onError: showError });
  const status = useMutation({ mutationFn: ({ id, value }: { id: string; value: SuspiciousListing["status"] }) => setSuspiciousListingStatus(id, value, accountId), onSuccess: refresh, onError: showError });
  const remove = useMutation({ mutationFn: (id: string) => deleteSuspiciousListing(id, accountId), onSuccess: () => { refresh(); toast.success("Anunț eliminat din listă"); }, onError: showError });
  const saveMessage = useMutation({ mutationFn: ({ id, text }: { id: string; text: string }) => saveSuspiciousListingMessage(id, text, accountId), onSuccess: () => { refresh(); toast.success("Mesaj actualizat"); }, onError: showError });

  if (query.isLoading) return <AppShell><PageHeader title="Verificări anunțuri" description="Încărcăm regulile și cazurile locale…" /></AppShell>;
  if (query.isError || !query.data) return <AppShell><PageHeader title="Verificări anunțuri" description="Analiză locală pentru cazuri ce necesită verificare." /><EmptyState icon={<ShieldAlert className="h-6 w-6" />} title="Lista nu poate fi încărcată" description={query.error instanceof Error ? query.error.message : "Încearcă din nou."} /></AppShell>;

  const data = query.data;
  return (
    <AppShell>
      <PageHeader
        title="Verificări anunțuri"
        description={`Analiză asistată pentru ${data.account_label}. Confirmarea unei sesizări rămâne manuală.`}
      />
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(330px,0.9fr)]">
        <section className="space-y-6">
          <AddListingForm submitting={add.isPending} onSubmit={(value) => add.mutate(value)} />
          <Listings items={data.listings} onStatus={(id, value) => status.mutate({ id, value })} onDelete={(id) => remove.mutate(id)} onSaveMessage={(id, text) => saveMessage.mutate({ id, text })} />
        </section>
        <RulesForm rules={data.rules} saving={saveRules.isPending} onSubmit={(value) => saveRules.mutate(value)} />
      </div>
    </AppShell>
  );
}

function AddListingForm({ submitting, onSubmit }: { submitting: boolean; onSubmit: (value: typeof EMPTY_LISTING) => void }) {
  const [draft, setDraft] = useState(EMPTY_LISTING);
  function submit(event: FormEvent) { event.preventDefault(); onSubmit(draft); setDraft(EMPTY_LISTING); }
  return <Card className="overflow-hidden border-primary/20 shadow-[0_18px_50px_-35px_oklch(0.42_0.12_55/0.6)]">
    <CardHeader className="border-b border-border/70 bg-muted/25 pb-4"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground"><SearchCheck className="h-4 w-4" /></span><div><CardTitle className="font-display text-base">Analizează un anunț</CardTitle><p className="mt-1 text-xs text-muted-foreground">Introdu datele pe care le-ai verificat; scorul explică exact ce a coincis cu regulile.</p></div></div></CardHeader>
    <CardContent className="p-5"><form className="grid gap-4 sm:grid-cols-2" onSubmit={submit}>
      <Field label="Titlul anunțului *"><Input required value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Ex.: Acme Widget Producător" /></Field>
      <Field label="Link OLX"><Input type="url" value={draft.url} onChange={(e) => setDraft({ ...draft, url: e.target.value })} placeholder="https://www.olx.ro/d/oferta/..." /></Field>
      <Field label="Preț"><Input type="number" min="0" value={draft.price ?? ""} onChange={(e) => setDraft({ ...draft, price: e.target.value === "" ? null : Number(e.target.value) })} placeholder="0" /></Field>
      <Field label="Monedă"><Input maxLength={8} value={draft.currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value.toUpperCase() })} /></Field>
      <div className="sm:col-span-2"><Field label="Descriere / informații observate"><Textarea className="min-h-24 resize-y" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="Copiază numai detaliile relevante pentru verificare…" /></Field></div>
      <div className="sm:col-span-2 flex justify-end"><Button disabled={submitting} type="submit"><Plus className="mr-1" />{submitting ? "Analizez…" : "Adaugă și analizează"}</Button></div>
    </form></CardContent>
  </Card>;
}

function RulesForm({ rules, saving, onSubmit }: { rules: SuspiciousRules; saving: boolean; onSubmit: (value: SuspiciousRules) => void }) {
  const [draft, setDraft] = useState(rules);
  function submit(event: FormEvent) { event.preventDefault(); onSubmit({ ...draft, max_price: draft.max_price === null || draft.max_price === 0 ? null : Number(draft.max_price) }); }
  return <Card className="sticky top-6"><CardHeader className="border-b border-border/70 pb-4"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200"><Settings2 className="h-4 w-4" /></span><div><CardTitle className="font-display text-base">Reguli de analiză</CardTitle><p className="mt-1 text-xs text-muted-foreground">Schimbarea regulilor recalculează lista.</p></div></div></CardHeader><CardContent className="p-5"><form className="space-y-4" onSubmit={submit}>
    <Field label="Titluri urmărite"><Textarea className="min-h-20" value={draft.watched_titles} onChange={(e) => setDraft({ ...draft, watched_titles: e.target.value })} placeholder="Un titlu pe rând" /></Field>
    <Field label="Prag maxim de preț"><Input type="number" min="0" value={draft.max_price ?? ""} onChange={(e) => setDraft({ ...draft, max_price: e.target.value === "" ? null : Number(e.target.value) })} placeholder="Lasă gol pentru dezactivare" /></Field>
    <Field label="Expresii de verificat"><Textarea className="min-h-24" value={draft.suspicious_terms} onChange={(e) => setDraft({ ...draft, suspicious_terms: e.target.value })} placeholder="Câte o expresie pe rând" /></Field>
    <div><Label className="text-xs">Motive active</Label><div className="mt-2 space-y-2 rounded-xl border border-border/70 p-3">
      {([
        ["pret_redus", "Preț mult sub pragul tău"],
        ["plata_avans", "Plată în avans / transfer direct"],
        ["contact_extern", "Contact în afara platformei"],
        ["descriere_suspecta", "Expresii configurate"],
      ] as const).map(([key, label]) => <label key={key} className="flex cursor-pointer items-center gap-2.5 text-xs font-medium"><Checkbox checked={draft.selected_reasons.includes(key)} onCheckedChange={(checked) => setDraft({ ...draft, selected_reasons: checked ? [...draft.selected_reasons, key] : draft.selected_reasons.filter((value) => value !== key) })} />{label}</label>)}
    </div></div>
    <Field label="Motiv propus"><Input value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} /></Field>
    <Field label="Mesaj propus"><Textarea className="min-h-28" value={draft.message_template} onChange={(e) => setDraft({ ...draft, message_template: e.target.value })} /><p className="mt-1 text-[10px] text-muted-foreground">Poți folosi <code>{"{title}"}</code> și <code>{"{signals}"}</code>.</p></Field>
    <Button className="w-full" disabled={saving} type="submit">{saving ? "Salvez…" : "Salvează regulile"}</Button>
  </form></CardContent></Card>;
}

function Listings({ items, onStatus, onDelete, onSaveMessage }: { items: SuspiciousListing[]; onStatus: (id: string, status: SuspiciousListing["status"]) => void; onDelete: (id: string) => void; onSaveMessage: (id: string, text: string) => void }) {
  if (!items.length) return <EmptyState icon={<Flag className="h-6 w-6" />} title="Nu ai încă anunțuri de verificat" description="Adaugă un anunț dintr-o căutare sau dintr-un link OLX pentru a-l evalua cu regulile tale." />;
  return <section className="space-y-3"><div className="flex items-baseline justify-between px-1"><h2 className="font-display text-lg font-bold">Cazuri analizate</h2><span className="font-mono text-xs text-muted-foreground">{items.length} în listă</span></div>{items.map((item) => <ListingCard key={item.id} item={item} onStatus={onStatus} onDelete={onDelete} onSaveMessage={onSaveMessage} />)}</section>;
}

function ListingCard({ item, onStatus, onDelete, onSaveMessage }: { item: SuspiciousListing; onStatus: (id: string, status: SuspiciousListing["status"]) => void; onDelete: (id: string) => void; onSaveMessage: (id: string, text: string) => void }) {
  const [copied, setCopied] = useState(false);
  const [message, setMessage] = useState(item.suggested_message);
  const tone = item.score >= 65 ? "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-200" : item.score >= 30 ? "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200" : "bg-slate-100 text-slate-700 dark:bg-slate-500/15 dark:text-slate-200";
  async function copy() { await navigator.clipboard.writeText(message); setCopied(true); toast.success("Mesaj copiat"); window.setTimeout(() => setCopied(false), 1800); }
  return <Card className="overflow-hidden"><CardContent className="p-0"><div className="flex gap-4 p-5"><div className={cn("grid h-14 w-14 shrink-0 place-items-center rounded-2xl font-mono text-xl font-bold tabular-nums", tone)}>{item.score}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-start justify-between gap-2"><div className="min-w-0"><h3 className="truncate font-display text-base font-bold">{item.title}</h3><p className="mt-1 text-xs text-muted-foreground">{item.price !== null ? formatPrice(item.price, item.currency) : "Preț nespecificat"} · {item.reason}</p></div><StatusPill status={item.status} /></div><div className="mt-3 flex flex-wrap gap-1.5">{item.signals.length ? item.signals.map((signal) => <span key={signal.text} className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">{signal.text}</span>) : <span className="text-xs text-muted-foreground">Nu corespunde încă niciunui semnal configurat.</span>}</div></div></div>
    <div className="border-t border-border/70 bg-muted/15 px-5 py-4"><Label className="text-[10px] font-semibold uppercase tracking-[0.13em] text-muted-foreground">Mesaj propus — editabil înainte de utilizare</Label><Textarea className="mt-2 min-h-20 bg-background/70 text-xs leading-relaxed" value={message} onChange={(event) => setMessage(event.target.value)} /><div className="mt-4 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => onSaveMessage(item.id, message)}>Salvează mesajul</Button><Button size="sm" variant="outline" onClick={copy}>{copied ? <Check /> : <Clipboard />}{copied ? "Copiat" : "Copiază mesajul"}</Button>{item.url ? <Button size="sm" variant="outline" asChild><a href={item.url} target="_blank" rel="noreferrer"><ExternalLink />Deschide anunțul</a></Button> : null}{item.status !== "verificat" ? <Button size="sm" variant="outline" onClick={() => onStatus(item.id, "verificat")}><Check />Verificat</Button> : null}{item.status !== "fals_positiv" ? <Button size="sm" variant="ghost" onClick={() => onStatus(item.id, "fals_positiv")}><X />Fals pozitiv</Button> : null}<Button className="ml-auto" size="sm" variant="ghost" onClick={() => onDelete(item.id)}><Trash2 />Șterge</Button></div></div>
  </CardContent></Card>;
}

function StatusPill({ status }: { status: SuspiciousListing["status"] }) { const labels = { de_verificat: "De verificat", verificat: "Verificat", fals_positiv: "Fals pozitiv" }; return <span className="rounded-full border border-border bg-background px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.11em] text-muted-foreground">{labels[status]}</span>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div><Label className="text-xs" >{label}</Label><div className="mt-1.5">{children}</div></div>; }
function showError(error: unknown) { toast.error(error instanceof Error ? error.message : "Acțiunea nu a putut fi finalizată"); }
