import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Switch elegant light/dark. Tema initiala e aplicata inainte de paint de
 * scriptul din __root.tsx (fara flash). Aici doar sincronizam si comutam.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [mounted, setMounted] = useState(false);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
    setMounted(true);
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* localStorage indisponibil — ignoram */
    }
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Comută tema"
      onClick={toggle}
      className={cn(
        "group relative inline-flex h-8 w-[3.75rem] items-center rounded-full p-1",
        "border border-border/70 bg-muted/60",
        "transition-colors duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        className,
      )}
    >
      {/* thumb glisant */}
      <span
        className={cn(
          "relative z-10 grid h-6 w-6 place-items-center rounded-full bg-card",
          "shadow-[0_1px_2px_oklch(0.25_0.02_230/0.2)]",
          "transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
          mounted && dark ? "translate-x-[1.75rem]" : "translate-x-0",
        )}
      >
        <Sun
          className={cn(
            "absolute h-3.5 w-3.5 text-amber-500 transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
            dark ? "scale-0 -rotate-90 opacity-0" : "scale-100 rotate-0 opacity-100",
          )}
          strokeWidth={1.75}
        />
        <Moon
          className={cn(
            "absolute h-3.5 w-3.5 text-primary transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
            dark ? "scale-100 rotate-0 opacity-100" : "scale-0 rotate-90 opacity-0",
          )}
          strokeWidth={1.75}
        />
      </span>
    </button>
  );
}
