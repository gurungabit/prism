import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const CHUNK_GROUPS: Array<{
  name: string;
  matches: Array<string | RegExp>;
}> = [
  {
    name: "react-vendor",
    matches: ["react", "react-dom", "scheduler", "react-is", "use-sync-external-store"],
  },
  {
    name: "router",
    matches: [
      "@tanstack/react-router",
      "@tanstack/router-core",
      "@tanstack/history",
      "@tanstack/store",
      "@tanstack/react-store",
    ],
  },
  {
    name: "state-data",
    matches: ["@tanstack/react-query", "@tanstack/query-core", "zustand", "zod"],
  },
  {
    name: "ui-utils",
    matches: ["lucide-react", "clsx", "tailwind-merge"],
  },
  {
    name: "pdf-utils",
    matches: [
      "jspdf",
      "jspdf-autotable",
      "fflate",
      "fast-png",
    ],
  },
  {
    name: "markdown",
    matches: [
      "streamdown",
      "marked",
      "parse5",
      "rehype-raw",
      "rehype-sanitize",
      "rehype-harden",
      "remark-gfm",
      "remark-parse",
      "remark-rehype",
      "unified",
      "vfile",
      "vfile-location",
      "vfile-message",
      /^micromark/,
      /^mdast-util/,
      /^hast-util/,
      /^unist-util/,
      "property-information",
      "web-namespaces",
      "comma-separated-tokens",
      "space-separated-tokens",
      "html-url-attributes",
      "html-void-elements",
      "entities",
      "ccount",
      "devlop",
      "bail",
      "trough",
      "zwitch",
      "longest-streak",
      "markdown-table",
      "trim-lines",
      "decode-named-character-reference",
      "style-to-js",
      "style-to-object",
      "inline-style-parser",
      "hastscript",
      "extend",
      "is-plain-obj",
      "remend",
      "seroval",
      "seroval-plugins",
      "@ungap/structured-clone",
      // Pull shiki + @streamdown/code into the markdown chunk so the
      // circular ``misc-vendor -> markdown -> misc-vendor`` warning
      // resolves: previously ``streamdown`` lived here but its
      // ``@streamdown/code`` peer (which depends on shiki) landed in
      // misc-vendor, creating the back-edge. Code highlighting is
      // only used by the markdown renderer in chat/analyze, so it
      // belongs in the same chunk as the markdown pipeline.
      "@streamdown/code",
      "shiki",
      /^@shikijs/,
    ],
  },
  {
    // Graph / layout libraries used by /organization and the
    // blast-radius view in /analyze. Pulling these out of misc-vendor
    // is the single biggest payload win after shiki -- ``@xyflow/react``
    // alone is ~4.6 MB on disk and ``@dagrejs/dagre`` is ~2 MB.
    //
    // The match list has to cover the *whole* graph dependency
    // island, not just the public packages. Round 17 missed the
    // transitives (``@xyflow/system``, ``classcat``, ``@dagrejs/graphlib``)
    // and they fell into ``misc-vendor``, creating a circular
    // ``misc-vendor -> graph -> misc-vendor`` warning because
    // ``@xyflow/react`` (in ``graph``) imported ``@xyflow/system``
    // (in ``misc-vendor``) which imported other ``@xyflow`` modules
    // back in ``graph``. Round 18 widens to the full island.
    name: "graph",
    matches: [
      // Whole xyflow scope -- catches ``@xyflow/react``,
      // ``@xyflow/system``, and any future sibling packages.
      /^@xyflow\//,
      // Whole dagrejs scope -- catches ``@dagrejs/dagre`` and
      // ``@dagrejs/graphlib``.
      /^@dagrejs\//,
      "dagre",
      // ``classcat`` is xyflow's class-name helper; only xyflow
      // uses it in this tree.
      "classcat",
      // d3 sub-packages xyflow uses for force layout. They're
      // tiny individually but they cluster -- group them with
      // the consumer.
      /^d3-/,
    ],
  },
];

function getPackageName(id: string): string | undefined {
  const normalized = id.split("/node_modules/")[1];
  if (!normalized) return undefined;

  const segments = normalized.split("/");
  if (segments[0]?.startsWith("@")) {
    return `${segments[0]}/${segments[1]}`;
  }
  return segments[0];
}

function matchesPattern(packageName: string, pattern: string | RegExp) {
  return typeof pattern === "string" ? packageName === pattern : pattern.test(packageName);
}

function manualChunk(id: string) {
  if (!id.includes("node_modules")) return undefined;

  const packageName = getPackageName(id);
  if (!packageName) return undefined;

  const group = CHUNK_GROUPS.find(({ matches }) =>
    matches.some((pattern) => matchesPattern(packageName, pattern)),
  );

  return group?.name ?? "misc-vendor";
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      html2canvas: fileURLToPath(new URL("./src/lib/pdfOptional/html2canvas.ts", import.meta.url)),
      dompurify: fileURLToPath(new URL("./src/lib/pdfOptional/dompurify.ts", import.meta.url)),
      canvg: fileURLToPath(new URL("./src/lib/pdfOptional/canvg.ts", import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: manualChunk,
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
