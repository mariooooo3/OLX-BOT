import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Download, RefreshCw, RotateCw } from "lucide-react";

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

      <div className="max-w-2xl space-y-6">
        {needsRestart && (
          <div className="reveal flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3">
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
              className="gap-1.5"
              disabled={restart.isPending}
              onClick={() => restart.mutate()}
            >
              <RotateCw className={`h-4 w-4 ${restart.isPending ? "animate-spin" : ""}`} />
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
                      className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                      onClick={() => {
                        qc.invalidateQueries({ queryKey: ["llmModels"] });
                        models.refetch();
                      }}
                    >
                      <RefreshCw className="h-3 w-3" />
                      Reîmprospătează
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
                            Ollama nu rulează (instalează de pe ollama.com)
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
                            Cheie Groq lipsă (gratuită pe console.groq.com, se
                            pune în .env la GROQ_API_KEY)
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
                  <Button type="submit" disabled={save.isPending}>
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
                Ollama nu rulează pe acest calculator. Instalează-l de pe{" "}
                <a
                  href="https://ollama.com/download"
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-2"
                >
                  ollama.com/download
                </a>
                , pornește-l, apoi revino aici ca să descarci modele.
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
                    disabled={!pullName.trim() || startPull.isPending}
                    onClick={() => startPull.mutate(pullName.trim())}
                    className="gap-1.5"
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
                      className="h-7 text-xs"
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
    </AppShell>
  );
}
