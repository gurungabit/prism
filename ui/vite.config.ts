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
