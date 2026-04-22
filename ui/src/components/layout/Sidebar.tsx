import { useState } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Database,
  Search,
  FlaskConical,
  MessageCircle,
  History,
  Network,
  PanelLeftClose,
  PanelLeft,
  Triangle,
} from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/organization", label: "Organization", icon: Network },
  { to: "/analyze", label: "Analyze", icon: FlaskConical },
  { to: "/search", label: "Search", icon: Search },
  { to: "/chat", label: "Chat", icon: MessageCircle },
  { to: "/sources", label: "Sources", icon: Database },
  { to: "/history", label: "History", icon: History },
] as const;

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  return (
    <aside
      className={`
        flex flex-col h-screen border-r border-zinc-200/70 dark:border-zinc-700/40
        bg-white dark:bg-[#1a1a1c]
        transition-[width] duration-200 ease-out
        ${collapsed ? "w-[52px]" : "w-52"}
      `}
    >
      <div
        className={`
          flex items-center h-12
          ${collapsed ? "flex-col-reverse h-auto gap-1 py-2 px-1.5" : "justify-between px-4"}
        `}
      >
        <Link
          to="/"
          aria-label="PRISM home"
          className="flex items-center gap-2 rounded-md -mx-1 px-1 py-1 transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-700/30"
        >
          <Triangle className="w-4 h-4 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)] flex-shrink-0" />
          {!collapsed && (
            <span className="text-[13px] font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
              PRISM
            </span>
          )}
        </Link>
        <button
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex items-center justify-center rounded-lg p-1.5 text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-700/30 transition-colors duration-150"
        >
          {collapsed ? (
            <PanelLeft className="w-3.5 h-3.5" />
          ) : (
            <PanelLeftClose className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto" role="navigation">
        {navItems.map(({ to, label, icon: Icon }) => {
          const isActive =
            to === "/" ? currentPath === "/" : currentPath.startsWith(to);

          return (
            <Link
              key={to}
              to={to}
              className={`
                flex items-center gap-2.5 mx-1.5 rounded-lg
                transition-all duration-150
                ${collapsed ? "justify-center px-0 py-2" : "px-3 py-[7px]"}
                ${
                  isActive
                    ? "bg-[var(--color-accent-muted)] text-[var(--color-accent)] dark:bg-[var(--color-accent-dark-muted)] dark:text-[var(--color-accent-dark)]"
                    : "text-zinc-400 dark:text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-700/30"
                }
              `}
              title={collapsed ? label : undefined}
              aria-label={label}
              aria-current={isActive ? "page" : undefined}
            >
              <Icon className="w-[16px] h-[16px] flex-shrink-0" />
              {!collapsed && (
                <span className="text-[13px] font-medium">{label}</span>
              )}
            </Link>
          );
        })}
      </nav>

    </aside>
  );
}
