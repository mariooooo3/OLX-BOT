import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ExternalLink, Loader2, MapPin, Search, SearchX, User } from "lucide-react";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { searchListings } from "@/lib/api";
import type { ListingSearchResponse, ListingSearchResult } from "@/lib/types";
import { formatPrice } from "@/lib/format";

export const Route = createFileRoute("/listing-search")({
  head: () => ({ meta: [{ title: "Căutare anunțuri — OLX Bot" }] }),
  component: ListingSearchPage,
});

// o pagina de rezultate OLX are ~51 anunturi — verificam primele 20 implicit,
// ca un raspuns tipic sa nu dureze peste ~30-40s (o pagina de detaliu per
// candidat, secvential)
const DEFAULT_LIMIT = 20;

function ListingSearchPage() {
  const [query, setQuery] = useState("");
  const search = useMutation({
    mutationFn: (q: string) => searchListings(q, DEFAULT_LIMIT),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;
    search.mutate(q);
  }

  return (
    <AppShell>
      <PageHeader
        title="Căutare anunțuri"
        description="Vezi toate anunțurile OLX care conțin un titlu anume, mai puțin cele ale conturilor tale."
      />

      <Card className="overflow-hidden">
        <CardContent className="p-5">
          <form className="flex gap-2" onSubmit={submit}>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ex.: iphone 12 pro"
              className="flex-1"
              autoFocus
            />
            <Button type="submit" disabled={!query.trim() || search.isPending}>
              {search.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.5} />
              ) : (
                <Search className="mr-1.5 h-4 w-4" strokeWidth={1.5} />
              )}
              {search.isPending ? "Caut…" : "Caută"}
            </Button>
          </form>
          {search.isPending ? (
            <p className="mt-3 text-xs text-muted-foreground">
              Verific fiecare anunț în parte ca să știu cine e vânzătorul — poate dura până la un
              minut pentru căutări cu multe rezultate.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="mt-6">
        {search.isError ? (
          <EmptyState
            icon={<SearchX className="h-6 w-6" />}
            title="Căutarea nu a putut fi finalizată"
            description={
              search.error instanceof Error ? search.error.message : "Încearcă din nou."
            }
          />
        ) : search.data ? (
          <Results data={search.data} />
        ) : !search.isPending ? (
          <EmptyState
            icon={<Search className="h-6 w-6" />}
            title="Caută un titlu"
            description="Scrie un titlu sau un cuvânt-cheie și apasă Caută — vezi toate anunțurile OLX care îl conțin."
          />
        ) : null}
      </div>
    </AppShell>
  );
}

function Results({ data }: { data: ListingSearchResponse }) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="font-display text-lg font-bold">
          {data.listings.length} {data.listings.length === 1 ? "anunț" : "anunțuri"} pentru „
          {data.query}”
        </h2>
        <span className="font-mono text-xs text-muted-foreground">
          {data.checked} verificate
          {data.excluded_own > 0
            ? ` · ${data.excluded_own} ${data.excluded_own === 1 ? "exclus (al tău)" : "excluse (ale tale)"}`
            : ""}
        </span>
      </div>

      {data.listings.length === 0 ? (
        <EmptyState
          icon={<SearchX className="h-6 w-6" />}
          title="Niciun anunț găsit"
          description={
            data.excluded_own > 0
              ? "Toate rezultatele verificate păreau să fie ale tale — au fost excluse."
              : "Încearcă un alt titlu sau cuvânt-cheie."
          }
        />
      ) : (
        <div className="space-y-2.5">
          {data.listings.map((item) => (
            <ListingCard key={item.url} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}

function ListingCard({ item }: { item: ListingSearchResult }) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="flex flex-wrap items-center gap-4 p-4">
        <div className="min-w-0 flex-1">
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 font-display text-sm font-bold hover:underline"
          >
            {item.title}
            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.5} />
          </a>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {item.seller_name ? (
              <span className="inline-flex items-center gap-1">
                <User className="h-3 w-3" strokeWidth={1.5} />
                {item.seller_name}
              </span>
            ) : null}
            {item.location_date ? (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3 w-3" strokeWidth={1.5} />
                {item.location_date}
              </span>
            ) : null}
          </div>
        </div>
        <div className="shrink-0 font-mono text-sm font-semibold tabular-nums">
          {item.price !== null && item.currency
            ? formatPrice(item.price, item.currency)
            : item.price_text ?? "—"}
        </div>
      </CardContent>
    </Card>
  );
}
