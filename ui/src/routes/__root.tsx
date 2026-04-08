import { Suspense } from "react";
import { Outlet } from "@tanstack/react-router";
import { Sidebar } from "../components/layout/Sidebar";
import { TopBar } from "../components/layout/TopBar";

function RouteSkeleton() {
  return (
    <div className="px-6 py-8">
      <div className="animate-pulse space-y-4">
        <div className="h-4 w-40 rounded bg-zinc-200 dark:bg-zinc-800" />
        <div className="h-24 rounded-2xl bg-zinc-100 dark:bg-zinc-900" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="h-32 rounded-2xl bg-zinc-100 dark:bg-zinc-900" />
          <div className="h-32 rounded-2xl bg-zinc-100 dark:bg-zinc-900" />
        </div>
      </div>
    </div>
  );
}

export function RootLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-[#fafaf9] dark:bg-[#131315]">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          <Suspense fallback={<RouteSkeleton />}>
            <div className="animate-fade-in">
              <Outlet />
            </div>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
