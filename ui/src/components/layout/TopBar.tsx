import { useRouterState } from "@tanstack/react-router";
import { ThemeToggle } from "./ThemeToggle";

const routeLabels: Record<string, string> = {
  "/": "Dashboard",
  "/sources": "Sources",
  "/search": "Search",
  "/analyze": "Analyze",
  "/chat": "Chat",
  "/history": "History",
};

export function TopBar() {
  const routerState = useRouterState();
  const path = routerState.location.pathname;

  const baseRoute = "/" + (path.split("/")[1] || "");
  const label = routeLabels[baseRoute] || routeLabels[path] || "PRISM";

  return (
    <header className="h-12 flex items-center justify-between px-6 border-b border-zinc-200/70 dark:border-zinc-700/40 bg-white/80 dark:bg-[#1a1a1c]/80 backdrop-blur-sm">
      <div className="flex items-center gap-2 text-[12px]">
        <span className="text-zinc-300 dark:text-zinc-600 font-medium">PRISM</span>
        <span className="text-zinc-200 dark:text-zinc-700">/</span>
        <span className="font-semibold text-zinc-700 dark:text-zinc-200 tracking-tight">
          {label}
        </span>
      </div>

      <ThemeToggle />
    </header>
  );
}
