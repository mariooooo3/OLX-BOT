import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Cloud,
  Cpu,
  Download,
  ExternalLink,
  RefreshCw,
  RotateCw,
} from "lucide-react";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getSettings,
  saveSettings,
  getLlmModels,
  pullOllamaModel,
  getOllamaPullStatus,
  getBotStatus,
  restartBot,
} from "@/lib/api";
import type { Settings } from "@/lib/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Setări — OLX Bot" },
      { name: "description", content: "Configurează botul OLX: interval poll, model LLM, log level." },
    ],
  }),
  component: SettingsPage,
});

// sugestii pentru descarcare — modele mici, potrivite pe un PC obisnuit
const SUGGESTED_MODELS = [
  { name: "llama3.1:8b", note: "echilibrat, ~4.9GB" },
  { name: "qwen2.5:7b", note: "bun pe română, ~4.7GB" },
  { name: "mistral:7b", note: "rapid, ~4.4GB" },
];

/** valoarea compusa a dropdown-ului: "ollama:llama3.1:8b" / "groq:llama..." */
function modelValue(form: Settings): string {
  return form.llm_backend === "ollama"
    ? `ollama:${form.ollama_model}`
    : `groq:${form.groq_model}`;
}

function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [form, setForm] = useState<Settings | null>(null);
  const [pullName, setPullName] = useState("");
  const [pulling, setPulling] = useState(false);

  const models = useQuery({
    queryKey: ["llmModels"],
    queryFn: () => getLlmModels(),
    staleTime: 60_000,
  });

  const botStatus = useQuery({
    queryKey: ["botStatus"],
    queryFn: getBotStatus,
    refetchInterval: 10_000,
  });

  // progresul descarcarilor — interogat doar cat timp exista un pull activ
  const pullStatus = useQuery({
    queryKey: ["ollamaPull"],
    queryFn: getOllamaPullStatus,
    refetchInterval: pulling ? 1500 : false,
    enabled: pulling,
  });

  useEffect(() => {
    if (q.data) setForm(q.data);
  }, [q.data]);

  const activePulls = useMemo(
    () =>
      Object.entries(pullStatus.data ?? {}).filter(([, job]) => !job.done),
    [pullStatus.data],
  );

  // cand toate pull-urile s-au terminat: oprim polling-ul si reimprospatam lista
  useEffect(() => {
    if (!pulling || !pullStatus.data) return;
    const jobs = Object.entries(pullStatus.data);
    if (jobs.length === 0 || jobs.every(([, job]) => job.done)) {
      setPulling(false);
      qc.invalidateQueries({ queryKey: ["llmModels"] });
      for (const [model, job] of jobs) {
        if (job.error) toast.error(`Descărcarea ${model} a eșuat: ${job.error}`);
        else toast.success(`Model descărcat: ${model}`);
      }
    }
  }, [pulling, pullStatus.data, qc]);

  const save = useMutation({
    mutationFn: (next: Settings) => saveSettings(next),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
      qc.invalidateQueries({ queryKey: ["botStatus"] });
      toast.success("Setări salvate");
    },
    onError: () => toast.error("Nu am putut salva setările"),
  });

  const startPull = useMutation({
    mutationFn: (model: string) => pullOllamaModel(model),
    onSuccess: (res, model) => {
      if (res.started || res.already_running) {
        setPulling(true);
        toast.info(`Descărcare pornită: ${model}`);
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const restart = useMutation({
    mutationFn: restartBot,
    onSuccess: (status) => {
      qc.setQueryData(["botStatus"], status);
      qc.invalidateQueries({ queryKey: ["botStatus"] });
      toast.success("Bot repornit cu noile setări");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // botul ruleaza cu alt model decat cel salvat -> oferim repornirea
  const savedModel = q.data ? modelValue(q.data) : null;
  const needsRestart = Boolean(
    botStatus.data?.running &&
      !botStatus.data.stopping &&
      botStatus.data.active_llm &&
      savedModel &&
      botStatus.data.active_llm !== savedModel,
  );

  const ollama = models.data?.ollama;
  const groq = models.data?.groq;

  return (
    <AppShell>
      <PageHeader
        title="Setări"
        description="Configurează comportamentul botului."
      />

      <div className="grid max-w-5xl gap-6 lg:grid-cols-[minmax(0,1fr)_330px] lg:items-start">
        <div className="space-y-6">
          {needsRestart && (
            <div className="reveal flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/40 bg-amber-500/10 px-4 py-3">
              <p className="text-sm">
                Botul rulează încă cu modelul{" "}
                <span className="font-mono font-medium">
                  {botStatus.data?.active_llm?.split(":").slice(1).join(":")}
                </span>
                . Repornește-l ca să aplici modelul salvat.
              </p>
              <Button
                type="button"
                size="sm"
                className="press gap-1.5"
                disabled={restart.isPending}
                onClick={() => restart.mutate()}
              >
                <RotateCw
                  className={`h-4 w-4 ${restart.isPending ? "animate-spin" : ""}`}
                />
                {restart.isPending ? "Se repornește…" : "Repornește botul"}
              </Button>
            </div>
          )}

          <Card className="reveal" style={{ "--i": 1 } as React.CSSProperties}>
            <CardHeader>
              <CardTitle className="text-base">Configurare bot</CardTitle>
            </CardHeader>
            <CardContent>
              {q.isLoading || !form ? (
                <div className="space-y-4">
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                </div>
              ) : (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    save.mutate(form);
                  }}
                  className="space-y-6"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <Label>Interval poll</Label>
                      <span className="font-mono text-sm font-medium tabular-nums">
                        {form.poll_interval_seconds} sec
                      </span>
                    </div>
                    <Slider
                      className="mt-3"
                      min={30}
                      max={300}
                      step={5}
                      value={[form.poll_interval_seconds]}
                      onValueChange={([v]) =>
                        setForm({ ...form, poll_interval_seconds: v })
                      }
                    />
                    <p className="mt-2 text-xs text-muted-foreground">
                      Cât de des verifică botul mesaje noi pe OLX. Se aplică din
                      mers, fără repornire.
                    </p>
                  </div>

                  <div>
                    <div className="flex items-center justify-between">
                      <Label>Model AI</Label>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="group h-7 gap-1.5 px-2 text-xs text-muted-foreground"
                        onClick={() => {
                          qc.invalidateQueries({ queryKey: ["llmModels"] });
                          models.refetch();
                        }}
                      >
                        <RefreshCw
                          className={cn(
                            "h-3 w-3 transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:rotate-180 group-active:rotate-[360deg]",
                            models.isFetching && "animate-spin",
                          )}
                        />
                        {models.isFetching ? "Se caută…" : "Reîmprospătează"}
                      </Button>
                    </div>
                    <Select
                      value={modelValue(form)}
                      onValueChange={(v) => {
                        const [backend, ...rest] = v.split(":");
                        const model = rest.join(":"); // numele Ollama contin ":"
                        setForm(
                          backend === "ollama"
                            ? { ...form, llm_backend: "ollama", ollama_model: model }
                            : { ...form, llm_backend: "groq", groq_model: model },
                        );
                      }}
                    >
                      <SelectTrigger className="mt-2">
                        <SelectValue placeholder="Alege modelul" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectLabel>Modele locale (Ollama)</SelectLabel>
                          {models.isLoading ? (
                            <SelectItem value="_loading" disabled>
                              Se încarcă…
                            </SelectItem>
                          ) : !ollama?.available ? (
                            <SelectItem value="_no_ollama" disabled>
                              Ollama nu rulează — vezi „Stare medii AI"
                            </SelectItem>
                          ) : ollama.models.length === 0 ? (
                            <SelectItem value="_no_models" disabled>
                              Niciun model descărcat încă
                            </SelectItem>
                          ) : (
                            ollama.models.map((m) => (
                              <SelectItem key={m.name} value={`ollama:${m.name}`}>
                                {m.name} ({m.size_gb} GB, local)
                              </SelectItem>
                            ))
                          )}
                        </SelectGroup>
                        <SelectGroup>
                          <SelectLabel>Modele online (Groq)</SelectLabel>
                          {models.isLoading ? (
                            <SelectItem value="_loading_groq" disabled>
                              Se încarcă…
                            </SelectItem>
                          ) : !groq?.available ? (
                            <SelectItem value="_no_groq_key" disabled>
                              Cheie Groq lipsă — vezi „Stare medii AI"
                            </SelectItem>
                          ) : (
                            groq.models.map((m) => (
                              <SelectItem key={m.name} value={`groq:${m.name}`}>
                                {m.name} (online{m.note ? `, ${m.note}` : ""})
                              </SelectItem>
                            ))
                          )}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <p className="mt-2 text-xs text-muted-foreground">
                      Modelele locale rulează pe calculatorul tău prin Ollama
                      (gratuit, fără internet). Cele online folosesc cheia Groq.
                      Dacă botul rulează, după salvare apare un buton de
                      repornire ca modelul nou să se aplice.
                    </p>
                  </div>

                  <div>
                    <Label>Nivel log</Label>
                    <Select
                      value={form.log_level}
                      onValueChange={(v) =>
                        setForm({ ...form, log_level: v as Settings["log_level"] })
                      }
                    >
                      <SelectTrigger className="mt-2">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="INFO">INFO (normal)</SelectItem>
                        <SelectItem value="DEBUG">DEBUG (detaliat, pentru probleme)</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="mt-2 text-xs text-muted-foreground">
                      Cât de detaliat scrie botul în logs/bot.log. Pune DEBUG doar
                      când ceva nu merge și vrei să vezi exact ce face botul.
                    </p>
                  </div>

                  <div className="flex justify-end">
                    <Button type="submit" className="press" disabled={save.isPending}>
                      {save.isPending ? "Se salvează…" : "Salvează setările"}
                    </Button>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>

          <Card className="reveal" style={{ "--i": 2 } as React.CSSProperties}>
            <CardHeader>
              <CardTitle className="text-base">Descarcă model local (Ollama)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {!ollama?.available ? (
                <p className="text-sm text-muted-foreground">
                  Ollama nu rulează pe acest calculator — urmează pașii din
                  panoul <span className="font-medium text-foreground">„Stare medii AI"</span>,
                  apoi revino aici ca să descarci modele.
                </p>
              ) : (
                <>
                  <div className="flex gap-2">
                    <Input
                      placeholder="ex. llama3.1:8b"
                      value={pullName}
                      onChange={(e) => setPullName(e.target.value)}
                    />
                    <Button
                      type="button"
                      className="press gap-1.5"
                      disabled={!pullName.trim() || startPull.isPending}
                      onClick={() => startPull.mutate(pullName.trim())}
                    >
                      <Download className="h-4 w-4" />
                      Descarcă
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTED_MODELS.map((s) => (
                      <Button
                        key={s.name}
                        type="button"
                        variant="outline"
                        size="sm"
                        className="press h-7 text-xs"
                        onClick={() => setPullName(s.name)}
                      >
                        {s.name} · {s.note}
                      </Button>
                    ))}
                  </div>
                  {activePulls.map(([model, job]) => (
                    <div key={model} className="space-y-1.5">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-mono">{model}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {job.percent > 0 ? `${job.percent}%` : job.status}
                        </span>
                      </div>
                      <Progress value={job.percent} />
                    </div>
                  ))}
                  <p className="text-xs text-muted-foreground">
                    Lista completă de modele:{" "}
                    <a
                      href="https://ollama.com/library"
                      target="_blank"
                      rel="noreferrer"
                      className="underline underline-offset-2"
                    >
                      ollama.com/library
                    </a>
                    . După descărcare, modelul apare automat la „Model AI".
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Panoul din dreapta: starea mediilor AI + pasii de configurare */}
        <aside
          className="reveal lg:sticky lg:top-10"
          style={{ "--i": 3 } as React.CSSProperties}
        >
          <div className="rounded-[1.65rem] bg-foreground/[0.035] p-1.5 ring-1 ring-foreground/[0.06]">
            <div className="rounded-[calc(1.65rem-0.375rem)] bg-card p-5 shadow-[inset_0_1px_1px_oklch(1_0_0/0.7),0_1px_2px_oklch(0.25_0.02_230/0.05)]">
              <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                Stare medii AI
              </div>

              <div className="mt-4 space-y-5">
                <EnvStatus
                  loading={models.isLoading}
                  ok={!!ollama?.available}
                  icon={<Cpu className="h-4 w-4" strokeWidth={1.5} />}
                  name="Ollama"
                  kind="local"
                  okText={
                    ollama?.models.length
                      ? `Activ · ${ollama.models.length} ${ollama.models.length === 1 ? "model descărcat" : "modele descărcate"}`
                      : "Activ · niciun model descărcat încă"
                  }
                  steps={[
                    <>
                      Instalează aplicația de pe{" "}
                      <ExternalTextLink href="https://ollama.com/download">
                        ollama.com/download
                      </ExternalTextLink>
                    </>,
                    "Pornește Ollama (rulează în fundal)",
                    "Revino aici și descarcă un model din cardul alăturat",
                  ]}
                  actionHref="https://ollama.com/download"
                  actionLabel="Descarcă Ollama"
                />

                <div className="h-px bg-border/70" />

                <EnvStatus
                  loading={models.isLoading}
                  ok={!!groq?.available}
                  icon={<Cloud className="h-4 w-4" strokeWidth={1.5} />}
                  name="Groq"
                  kind="online"
                  okText={`Cheie configurată · ${groq?.models.length ?? 0} modele disponibile`}
                  steps={[
                    <>
                      Creează o cheie gratuită pe{" "}
                      <ExternalTextLink href="https://console.groq.com/keys">
                        console.groq.com/keys
                      </ExternalTextLink>
                    </>,
                    <>
                      Pune cheia în fișierul{" "}
                      <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">
                        .env
                      </code>{" "}
                      la linia{" "}
                      <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">
                        GROQ_API_KEY=
                      </code>
                    </>,
                    "Repornește serverul (start.bat)",
                  ]}
                  actionHref="https://console.groq.com/keys"
                  actionLabel="Ia o cheie Groq"
                />
              </div>

              <p className="mt-5 text-[11px] leading-relaxed text-muted-foreground">
                Îți ajunge unul singur dintre cele două ca botul să răspundă:
                Ollama = gratuit, local, fără internet · Groq = online, rapid,
                cu cheie gratuită.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}

function ExternalTextLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-foreground underline decoration-border underline-offset-2 transition-colors hover:decoration-foreground"
    >
      {children}
    </a>
  );
}

function EnvStatus({
  loading,
  ok,
  icon,
  name,
  kind,
  okText,
  steps,
  actionHref,
  actionLabel,
}: {
  loading: boolean;
  ok: boolean;
  icon: React.ReactNode;
  name: string;
  kind: "local" | "online";
  okText: string;
  steps: React.ReactNode[];
  actionHref: string;
  actionLabel: string;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-full" />
      </div>
    );
  }
  return (
    <div>
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "grid h-8 w-8 place-items-center rounded-lg",
            ok
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
              : "bg-muted text-muted-foreground",
          )}
        >
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold tracking-tight">{name}</span>
            <span className="rounded-full bg-muted px-1.5 py-px font-mono text-[10px] text-muted-foreground">
              {kind}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              className={cn(
                "h-1.5 w-1.5 shrink-0 rounded-full",
                ok ? "live-dot bg-emerald-500" : "bg-red-400",
              )}
            />
            <span className="truncate">
              {ok ? okText : "Neconfigurat"}
            </span>
          </div>
        </div>
      </div>

      {!ok && (
        <div className="mt-3 space-y-3">
          <ol className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">
            {steps.map((step, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-px grid h-4 w-4 shrink-0 place-items-center rounded-full bg-muted font-mono text-[10px] font-semibold text-foreground/70">
                  {i + 1}
                </span>
                <span className="min-w-0">{step}</span>
              </li>
            ))}
          </ol>
          <Button
            asChild
            variant="outline"
            size="sm"
            className="press h-7 gap-1.5 text-xs"
          >
            <a href={actionHref} target="_blank" rel="noreferrer">
              {actionLabel}
              <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
            </a>
          </Button>
        </div>
      )}
    </div>
  );
}
