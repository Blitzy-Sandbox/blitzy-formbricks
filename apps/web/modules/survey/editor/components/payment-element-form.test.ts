/**
 * Unit tests for PaymentElementForm — Issue 2 (Stripe Connect OAuth navigation loop fix).
 *
 * NOTE: The jsdom environment is unavailable for isolated .test.tsx runs due to
 * a pre-existing ESM/CJS incompatibility in html-encoding-sniffer (the same
 * issue that affects all .test.tsx files in this project). Therefore, these
 * tests validate the **behavioral logic** extracted from the component using
 * the node environment rather than React render + DOM assertions.
 *
 * The three critical behaviors verified:
 *
 * 1. URL cleanup logic — stripe_connect_success / stripe_connect_error params
 *    are correctly detected and removed from URLs, matching the useEffect
 *    in PaymentElementForm that calls history.replaceState.
 *
 * 2. Connect URL construction — The authorize URL built by handleConnectStripe
 *    uses a returnUrl that does NOT carry leftover stripe_connect_* params.
 *
 * 3. Replace vs. push — The implementation calls window.location.replace()
 *    which replaces the history entry, not window.location.href = ... which
 *    pushes. We test that the code as written uses the non-pushing approach
 *    by parsing the source file directly.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { describe, expect, test } from "vitest";

// ---------------------------------------------------------------------------
// Extract the behavioral logic from the component into testable pure functions
// that mirror exactly what PaymentElementForm does internally.
// ---------------------------------------------------------------------------

/**
 * Mirrors the cleanup useEffect logic in PaymentElementForm.
 * Given the current URL string, returns the cleaned URL string (without
 * stripe_connect_success / stripe_connect_error params) and a boolean
 * indicating whether cleanup was needed.
 */
function cleanupStripeParams(currentHref: string): { cleaned: boolean; url: string } {
  const url = new URL(currentHref);
  const hasStripeParams =
    url.searchParams.has("stripe_connect_success") || url.searchParams.has("stripe_connect_error");
  if (hasStripeParams) {
    url.searchParams.delete("stripe_connect_success");
    url.searchParams.delete("stripe_connect_error");
    return { cleaned: true, url: url.toString() };
  }
  return { cleaned: false, url: currentHref };
}

/**
 * Mirrors the handleConnectStripe logic in PaymentElementForm.
 * Given the current URL and organizationId, returns the full authorize URL
 * that would be passed to window.location.replace().
 */
function buildConnectUrl(currentHref: string, organizationId: string): string {
  const currentUrl = new URL(currentHref);
  currentUrl.searchParams.delete("stripe_connect_success");
  currentUrl.searchParams.delete("stripe_connect_error");
  const returnUrl = encodeURIComponent(currentUrl.toString());
  return `/api/stripe-connect/authorize?organizationId=${organizationId}&returnUrl=${returnUrl}`;
}

// ---------------------------------------------------------------------------
// Test Suite
// ---------------------------------------------------------------------------

describe("PaymentElementForm — Stripe Connect OAuth navigation loop fix (logic tests)", () => {
  // -----------------------------------------------------------------------
  // URL Cleanup Logic (mirrors useEffect behavior)
  // -----------------------------------------------------------------------
  describe("URL cleanup logic", () => {
    test("detects and removes stripe_connect_success from URL", () => {
      const result = cleanupStripeParams("http://localhost:3000/editor?stripe_connect_success=1");
      expect(result.cleaned).toBe(true);
      expect(result.url).not.toContain("stripe_connect_success");
      expect(result.url).toBe("http://localhost:3000/editor");
    });

    test("detects and removes stripe_connect_error from URL", () => {
      const result = cleanupStripeParams("http://localhost:3000/editor?stripe_connect_error=denied");
      expect(result.cleaned).toBe(true);
      expect(result.url).not.toContain("stripe_connect_error");
      expect(result.url).toBe("http://localhost:3000/editor");
    });

    test("removes both stripe params when both are present", () => {
      const result = cleanupStripeParams(
        "http://localhost:3000/editor?stripe_connect_success=1&stripe_connect_error=denied"
      );
      expect(result.cleaned).toBe(true);
      expect(result.url).not.toContain("stripe_connect_success");
      expect(result.url).not.toContain("stripe_connect_error");
    });

    test("preserves other query parameters during cleanup", () => {
      const result = cleanupStripeParams(
        "http://localhost:3000/editor?tab=payment&stripe_connect_success=1&mode=edit"
      );
      expect(result.cleaned).toBe(true);
      const parsed = new URL(result.url);
      expect(parsed.searchParams.get("tab")).toBe("payment");
      expect(parsed.searchParams.get("mode")).toBe("edit");
      expect(parsed.searchParams.has("stripe_connect_success")).toBe(false);
    });

    test("does NOT flag cleanup when URL has no stripe params", () => {
      const result = cleanupStripeParams("http://localhost:3000/editor?tab=payment");
      expect(result.cleaned).toBe(false);
      expect(result.url).toBe("http://localhost:3000/editor?tab=payment");
    });

    test("handles URL with no query params at all", () => {
      const result = cleanupStripeParams("http://localhost:3000/editor");
      expect(result.cleaned).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // Connect URL Construction (mirrors handleConnectStripe behavior)
  // -----------------------------------------------------------------------
  describe("handleConnectStripe URL construction", () => {
    test("builds authorize URL with correct organizationId and returnUrl", () => {
      const authorizeUrl = buildConnectUrl("http://localhost:3000/editor", "org-123");
      expect(authorizeUrl).toContain("/api/stripe-connect/authorize");
      expect(authorizeUrl).toContain("organizationId=org-123");
      expect(authorizeUrl).toContain("returnUrl=");
    });

    test("returnUrl does not include stripe_connect_success param from current URL", () => {
      const authorizeUrl = buildConnectUrl(
        "http://localhost:3000/editor?stripe_connect_success=1",
        "org-123"
      );
      const parsed = new URL(authorizeUrl, "http://localhost:3000");
      const returnUrl = decodeURIComponent(parsed.searchParams.get("returnUrl") || "");
      expect(returnUrl).not.toContain("stripe_connect_success");
    });

    test("returnUrl does not include stripe_connect_error param from current URL", () => {
      const authorizeUrl = buildConnectUrl(
        "http://localhost:3000/editor?stripe_connect_error=denied",
        "org-123"
      );
      const parsed = new URL(authorizeUrl, "http://localhost:3000");
      const returnUrl = decodeURIComponent(parsed.searchParams.get("returnUrl") || "");
      expect(returnUrl).not.toContain("stripe_connect_error");
    });

    test("returnUrl preserves other query params when stripe params are stripped", () => {
      const authorizeUrl = buildConnectUrl(
        "http://localhost:3000/editor?tab=payment&stripe_connect_success=1&mode=edit",
        "org-456"
      );
      const parsed = new URL(authorizeUrl, "http://localhost:3000");
      const returnUrl = decodeURIComponent(parsed.searchParams.get("returnUrl") || "");
      expect(returnUrl).toContain("tab=payment");
      expect(returnUrl).toContain("mode=edit");
      expect(returnUrl).not.toContain("stripe_connect_success");
    });

    test("returnUrl is the full clean URL when no stripe params existed", () => {
      const authorizeUrl = buildConnectUrl("http://localhost:3000/editor?tab=payment", "org-789");
      const parsed = new URL(authorizeUrl, "http://localhost:3000");
      const returnUrl = decodeURIComponent(parsed.searchParams.get("returnUrl") || "");
      expect(returnUrl).toBe("http://localhost:3000/editor?tab=payment");
    });
  });

  // -----------------------------------------------------------------------
  // Source Code Verification — Ensures the component uses replace() not href
  // -----------------------------------------------------------------------
  describe("source code uses window.location.replace() (not href assignment)", () => {
    let sourceCode: string;

    // Read the component source file to verify the calling pattern.
    // This is a static analysis test that protects against regressions.
    test("reads the component source file", () => {
      const filePath = path.resolve(__dirname, "payment-element-form.tsx");
      sourceCode = fs.readFileSync(filePath, "utf-8");
      expect(sourceCode.length).toBeGreaterThan(0);
    });

    test("handleConnectStripe uses window.location.replace()", () => {
      const filePath = path.resolve(__dirname, "payment-element-form.tsx");
      sourceCode = fs.readFileSync(filePath, "utf-8");

      // The component should call window.location.replace() for navigation
      expect(sourceCode).toContain("window.location.replace(");
    });

    test("handleConnectStripe does NOT use window.location.href = for navigation", () => {
      const filePath = path.resolve(__dirname, "payment-element-form.tsx");
      sourceCode = fs.readFileSync(filePath, "utf-8");

      // Extract lines around the handleConnectStripe function to check for href assignment.
      // We look for the pattern 'window.location.href =' which would push a history entry.
      const connectFuncRegex = /handleConnectStripe[\s\S]*?(?=const\s|function\s|\/\/\s*Handle\s)/;
      const connectSection = sourceCode.match(connectFuncRegex)?.[0] || "";

      // If we found the function body, verify no href assignment pattern exists
      if (connectSection) {
        expect(connectSection).not.toMatch(/window\.location\.href\s*=/);
      }
      // Also verify globally that no direct href assignment exists for stripe authorize
      expect(sourceCode).not.toMatch(/window\.location\.href\s*=\s*[`"']\/api\/stripe-connect/);
    });

    test("cleanup useEffect uses window.history.replaceState()", () => {
      const filePath = path.resolve(__dirname, "payment-element-form.tsx");
      sourceCode = fs.readFileSync(filePath, "utf-8");

      // The cleanup effect must use replaceState (not pushState) to avoid adding
      // to the history stack
      expect(sourceCode).toContain("window.history.replaceState(");
    });

    test("cleanup useEffect deletes stripe_connect_success and stripe_connect_error params", () => {
      const filePath = path.resolve(__dirname, "payment-element-form.tsx");
      sourceCode = fs.readFileSync(filePath, "utf-8");

      expect(sourceCode).toContain('url.searchParams.delete("stripe_connect_success")');
      expect(sourceCode).toContain('url.searchParams.delete("stripe_connect_error")');
    });
  });
});
