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
const OrgDetailPage = lazyRouteComponent(() => import("./routes/orgs.$orgId"), "OrgDetailPage");
const TeamDetailPage = lazyRouteComponent(() => import("./routes/teams.$teamId"), "TeamDetailPage");
const ServiceDetailPage = lazyRouteComponent(
  () => import("./routes/services.$serviceId"),
  "ServiceDetailPage",
);
const SourceDetailPage = lazyRouteComponent(
  () => import("./routes/sources.$sourceId"),
  "SourceDetailPage",
);
const NewSourcePage = lazyRouteComponent(() => import("./routes/sources.new"), "NewSourcePage");
const OrganizationPage = lazyRouteComponent(
  () => import("./routes/organization"),
  "OrganizationPage",
);

const rootRoute = createRootRoute({
  component: RootLayout,
});

const searchRouteSearchSchema = z.object({
  q: z.string().catch("").default(""),
  page: z.coerce.number().int().min(1).catch(1).default(1),
  entityTypes: z.array(z.string()).catch([]).default([]),
  // Catalog scope (UUIDs from the declared org/team/service tree). Replaces
  // the old free-text ``team_hint`` / ``service_hint`` URL params.
  orgId: z.string().catch("").default(""),
  teamIds: z.array(z.string()).catch([]).default([]),
  serviceIds: z.array(z.string()).catch([]).default([]),
});

const searchRouteDefaultValues = {
  q: "",
  page: 1,
  entityTypes: [] as string[],
  orgId: "",
  teamIds: [] as string[],
  serviceIds: [] as string[],
};

const newSourceSearchSchema = z.object({
  scope: z.enum(["org", "team", "service"]).optional(),
  scopeId: z.string().optional(),
});

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

const newSourceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sources/new",
  validateSearch: (search: SearchSchemaInput) => newSourceSearchSchema.parse(search),
  component: NewSourcePage,
});

const sourceDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sources/$sourceId",
  component: SourceDetailPage,
});

const orgDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/orgs/$orgId",
  component: OrgDetailPage,
});

const teamDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/teams/$teamId",
  component: TeamDetailPage,
});

const serviceDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/services/$serviceId",
  component: ServiceDetailPage,
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

const organizationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/organization",
  component: OrganizationPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  orgDetailRoute,
  teamDetailRoute,
  serviceDetailRoute,
  // /sources/new must come before /sources/$sourceId in the route tree so
  // TanStack matches the literal segment first.
  newSourceRoute,
  sourceDetailRoute,
  sourcesRoute,
  searchRoute,
  analyzeRoute,
  analyzeRunRoute,
  chatRoute,
  chatConversationRoute,
  historyRoute,
  organizationRoute,
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
