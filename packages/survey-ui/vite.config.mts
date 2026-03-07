/// <reference types="vitest" />
import path from "node:path";
import { defineConfig } from "vite";
import dts from "vite-plugin-dts";
import tsconfigPaths from "vite-tsconfig-paths";
import tailwindcss from "@tailwindcss/vite";

/**
 * Plugin to strip "use client" directives from bundled dependencies.
 *
 * This fixes warnings from Radix UI and other packages that include "use client"
 * directives for Next.js React Server Components compatibility. When Vite bundles
 * these packages, it emits warnings because module-level directives aren't supported
 * in the bundled output.
 *
 * The "use client" directive is only relevant for Next.js RSC and doesn't affect
 * our library build, so it's safe to remove during bundling.
 *
 * Related issue: https://github.com/TanStack/query/issues/5175
 */

// Resolve monorepo root React to prevent duplicate copies in tests.
// The package has react 19.2.1 as devDependency while root has 19.2.3;
// react-dom and react must share the same instance for hooks to work.
const monorepoRoot = path.resolve(import.meta.dirname, "../..");

export default defineConfig({
  resolve: {
    dedupe: ["react", "react-dom", "react/jsx-runtime"],
  },
  build: {
    // Keep dist when running watch so surveys (and others) can resolve types during parallel go
    emptyOutDir: false,
    lib: {
      entry: "src/index.ts",
      formats: ["es"],
    },
    rollupOptions: {
      external: [
        "react",
        "react-dom",
        "react/jsx-runtime",
        /^@formkit\/auto-animate/,
        /^@radix-ui/,
        "class-variance-authority",
        "clsx",
        /^date-fns/,
        "isomorphic-dompurify",
        "lucide-react",
        /^react-day-picker/,
        "tailwind-merge",
      ],
      output: {
        preserveModules: true,
        preserveModulesRoot: "src",
        entryFileNames: "[name].js",
      },
    },
  },
  plugins: [
    tsconfigPaths(),
    dts({
      include: ["src"],
      exclude: ["**/*.stories.tsx", "**/*.test.{ts,tsx}", "**/story-helpers.tsx"],
    }),
    tailwindcss(),
  ],
  test: {
    environment: "node",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["dist/**", "node_modules/**"],
    alias: {
      // Force all test imports to use a single React copy from the monorepo
      // root, preventing "Invalid hook call" errors when component tests use
      // React hooks (useState, useEffect, etc.).
      react: path.resolve(monorepoRoot, "node_modules/react"),
      "react-dom": path.resolve(monorepoRoot, "node_modules/react-dom"),
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html", "lcov"],
      reportsDirectory: "./coverage",
      include: ["src/lib/**/*.ts"],
      exclude: ["**/*.test.{ts,tsx}", "**/*.stories.tsx"],
    },
  },
});

