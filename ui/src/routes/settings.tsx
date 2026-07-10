import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AppShell, PageHeader } from "@/components/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getSettings, saveSettings } from "@/lib/api";
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

function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [form, setForm] = useState<Settings | null>(null);

  useEffect(() => {
    if (q.data) setForm(q.data);
  }, [q.data]);

  const save = useMutation({
    mutationFn: (next: Settings) => saveSettings(next),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
      qc.invalidateQueries({ queryKey: ["botStatus"] });
      toast.success("Setări salvate");
    },
    onError: () => toast.error("Nu am putut salva setările"),
  });

  return (
    <AppShell>
      <PageHeader
        title="Setări"
        description="Configurează comportamentul botului."
      />

      <div className="max-w-2xl">
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
                    max={120}
                    step={5}
                    value={[form.poll_interval_seconds]}
                    onValueChange={([v]) =>
                      setForm({ ...form, poll_interval_seconds: v })
                    }
                  />
                  <p className="mt-2 text-xs text-muted-foreground">
                    Cât de des verifică botul mesaje noi pe OLX.
                  </p>
                </div>

                <div>
                  <Label>Model Groq</Label>
                  <Select
                    value={form.groq_model}
                    onValueChange={(v) => setForm({ ...form, groq_model: v })}
                  >
                    <SelectTrigger className="mt-2">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="llama-3.1-8b-instant">
                        llama-3.1-8b-instant (rapid)
                      </SelectItem>
                      <SelectItem value="llama-3.3-70b-versatile">
                        llama-3.3-70b-versatile (calitate)
                      </SelectItem>
                    </SelectContent>
                  </Select>
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
                      <SelectItem value="INFO">INFO</SelectItem>
                      <SelectItem value="DEBUG">DEBUG</SelectItem>
                    </SelectContent>
                  </Select>
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
      </div>
    </AppShell>
  );
}