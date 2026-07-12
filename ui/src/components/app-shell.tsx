import { Link, useRouterState } from "@tanstack/react-router";
import { LayoutDashboard, MessagesSquare, Package, Settings, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";
import { ServerStatusBanner } from "@/components/server-status-banner";
import {
  AccountMenu,
  accountDisplayName,
  useOlxSession,
} from "@/components/account-menu";
import type { CSSProperties, ReactNode } from "react";

type NavItem = {
  to: "/" | "/conversations" | "/products" | "/settings";
  label: string;
  icon: typeof LayoutDashboard;
  exact?: boolean;
};

const nav: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/conversations", label: "Conversații", icon: MessagesSquare },
  { to: "/products", label: "Produse", icon: Package },
  { to: "/settings", label: "Setări", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const isActive = (to: string, exact?: boolean) =>
    exact ? pathname === to : pathname === to || pathname.startsWith(to + "/");
  const session = useOlxSession().data;
  const olxConnected = session?.connected ?? false;
  const activeAccountName = session?.account
    ? accountDisplayName(session.account)
    : null;

  return (
    <div className="min-h-[100dvh] bg-background text-foreground">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        {/* click pe logo = meniul de conturi OLX (switch / adauga / sign out) */}
        <AccountMenu align="start">
          <button
            type="button"
            className="flex w-full items-center gap-3 px-5 py-6 text-left transition-opacity duration-300 hover:opacity-80"
          >
            <div className="relative grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[inset_0_1px_0_oklch(1_0_0/0.25),0_8px_16px_-8px_oklch(0.52_0.09_195/0.6)]">
              <Bot className="h-5 w-5" strokeWidth={1.5} />
              {/* bulina de stare: verde = cont OLX conectat, rosie = nu */}
              <span
                className={cn(
                  "absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full border-2 border-sidebar",
                  olxConnected ? "bg-emerald-500" : "bg-red-500",
                )}
              />
            </div>
            <div className="min-w-0">
              <div className="font-display text-sm font-bold leading-tight tracking-tight">
                OLX Bot
              </div>
              <div className="truncate text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {activeAccountName ?? "Panou admin"}
              </div>
            </div>
          </button>
        </AccountMenu>
        <nav className="flex-1 space-y-1 px-3 py-2">
          {nav.map((item, index) => {
            const active = isActive(item.to, item.exact);
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                style={{ "--i": index } as CSSProperties}
                className={cn(
                  "reveal group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium",
                  "transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-[inset_0_1px_0_oklch(1_0_0/0.5)]"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/40 hover:text-sidebar-foreground",
                )}
              >
                <span
                  className={cn(
                    "absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-full bg-primary",
                    "transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
                    active ? "opacity-100 scale-y-100" : "opacity-0 scale-y-0",
                  )}
                />
                <Icon
                  className="h-4 w-4 shrink-0 transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:translate-x-0.5"
                  strokeWidth={1.5}
                />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center justify-between border-t border-sidebar-border px-5 py-4">
          <span className="font-mono text-[11px] text-muted-foreground">v1.0</span>
          <ThemeToggle />
        </div>
      </aside>

      {/* Main content */}
      <div className="md:pl-60">
        <ServerStatusBanner />
        {/* Mobile top bar */}
        <div className="sticky top-0 z-20 flex items-center justify-between border-b border-border/70 bg-background/85 px-4 py-3 backdrop-blur-xl md:hidden">
          <AccountMenu align="start">
            <button type="button" className="flex items-center gap-2">
              <div className="relative grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-foreground">
                <Bot className="h-4 w-4" strokeWidth={1.5} />
                <span
                  className={cn(
                    "absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-background",
                    olxConnected ? "bg-emerald-500" : "bg-red-500",
                  )}
                />
              </div>
              <span className="font-display text-sm font-bold tracking-tight">OLX Bot</span>
            </button>
          </AccountMenu>
          <ThemeToggle />
        </div>
        <main className="mx-auto max-w-7xl px-4 py-6 pb-28 md:px-10 md:py-10 md:pb-12">
          {children}
        </main>
      </div>

      {/* Mobile bottom bar — floating glass island */}
      <nav className="fixed inset-x-4 bottom-4 z-30 rounded-2xl border border-border/70 bg-card/85 shadow-[0_2px_4px_oklch(0.25_0.02_230/0.05),0_28px_56px_-20px_oklch(0.25_0.02_230/0.2)] backdrop-blur-xl md:hidden">
        <div className="grid grid-cols-4">
          {nav.map((item) => {
            const active = isActive(item.to, item.exact);
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium",
                  "transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] active:scale-95",
                  active
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon
                  className={cn(
                    "h-5 w-5 transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
                    active && "-translate-y-0.5",
                  )}
                  strokeWidth={1.5}
                />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="reveal mb-8 grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4 sm:flex sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h1 className="truncate font-display text-[1.85rem] font-bold leading-none tracking-tight">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </header>
  );
}
