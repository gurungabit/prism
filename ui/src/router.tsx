import {
  createRouter,
  createRootRoute,
  createRoute,
  lazyRouteComponent,
  stripSearchParams,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { z } from "zod";
import { RootLayout } from "./routes/__root";

const DashboardPage = lazyRouteComponent(() => import("./routes/index"), "DashboardPage");
const SourcesPage = lazyRouteComponent(() => import("./routes/sources"), "SourcesPage");
const SearchPage = lazyRouteComponent(() => import("./routes/search"), "SearchPage");
const AnalyzePage = lazyRouteComponent(() => import("./routes/analyze"), "AnalyzePage");
const AnalyzeRunPage = lazyRouteComponent(() => import("./routes/analyze.$runId"), "AnalyzeRunPage");
const ChatPage = lazyRouteComponent(() => import("./routes/chat"), "ChatPage");
const ChatConversationPage = lazyRouteComponent(
  () => import("./routes/chat.$conversationId"),
  "ChatConversationPage",
);
const HistoryPage = lazyRouteComponent(() => import("./routes/history"), "HistoryPage");

const rootRoute = createRootRoute({
  component: RootLayout,
});

const searchRouteSearchSchema = z.object({
  q: z.string().catch("").default(""),
  page: z.coerce.number().int().min(1).catch(1).default(1),
  entityTypes: z.array(z.string()).catch([]).default([]),
  teams: z.array(z.string()).catch([]).default([]),
  services: z.array(z.string()).catch([]).default([]),
});

const searchRouteDefaultValues = {
  q: "",
  page: 1,
  entityTypes: [] as string[],
  teams: [] as string[],
  services: [] as string[],
};

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardPage,
});

const sourcesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sources",
  component: SourcesPage,
});

const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/search",
  validateSearch: (search: SearchSchemaInput) => searchRouteSearchSchema.parse(search),
  search: {
    middlewares: [stripSearchParams(searchRouteDefaultValues)],
  },
  component: SearchPage,
});

const analyzeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/analyze",
  component: AnalyzePage,
});

const analyzeRunRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/analyze/$runId",
  component: AnalyzeRunPage,
});

const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chat",
  component: ChatPage,
});

const chatConversationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chat/$conversationId",
  component: ChatConversationPage,
});

const historyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/history",
  component: HistoryPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  sourcesRoute,
  searchRoute,
  analyzeRoute,
  analyzeRunRoute,
  chatRoute,
  chatConversationRoute,
  historyRoute,
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  defaultPreloadStaleTime: 30_000,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
