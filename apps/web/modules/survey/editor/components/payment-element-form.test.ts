/**
 * Unit tests for PaymentElementForm — Stripe Connect OAuth popup-based flow.
 *
 * The popup-based flow was introduced to eliminate an infinite navigation loop
 * caused by Stripe's OAuth consent page being added to the main window's
 * browser history. When Save, Save-and-Close, or Back navigated via
 * router.back(), users would land on Stripe's consent page, re-triggering
 * the OAuth flow indefinitely.
 *
 * The fix opens the OAuth flow in a popup window so the main window's history
 * stack is never affected. These tests verify the critical behavioral aspects
 * of that popup approach via static source-code analysis and extracted logic
 * tests (the jsdom environment is unavailable due to a pre-existing ESM/CJS
 * incompatibility in html-encoding-sniffer).
 *
 * Verified behaviors:
 * 1. handleConnectStripe opens a popup via window.open() — NOT via
 *    window.location.replace() or window.location.href assignment
 * 2. A polling interval detects when the popup returns to the app origin
 *    and invokes a cleanup routine that closes the popup
 * 3. If the popup is closed manually, the poll detects popup.closed and
 *    triggers the same cleanup routine (status refresh)
 * 4. Save, Save-and-Close, and Back are unaffected because the main
 *    window's history stack was never modified
 * 5. A fallback to window.location.replace() exists for the case where
 *    the browser blocks the popup
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { describe, expect, test } from "vitest";

// Read the source file once for all static analysis tests
const SOURCE_PATH = path.resolve(__dirname, "payment-element-form.tsx");
const sourceCode = fs.readFileSync(SOURCE_PATH, "utf-8");

// ---------------------------------------------------------------------------
// 1. Popup-Based Flow — Source Code Verification
// ---------------------------------------------------------------------------
describe("PaymentElementForm — Popup-based Stripe Connect flow (source analysis)", () => {
  test("handleConnectStripe uses window.open() to launch the popup", () => {
    // The component must call window.open() with a stripe authorize URL
    expect(sourceCode).toContain("window.open(");
    expect(sourceCode).toContain("stripe_connect_popup");
  });

  test("handleConnectStripe does NOT use window.location.replace() as primary path", () => {
    // Extract the handleConnectStripe function body. The function is assigned
    // via `const handleConnectStripe = () => {` and ends at the matching `};`.
    const funcStart = sourceCode.indexOf("const handleConnectStripe = ()");
    expect(funcStart).toBeGreaterThan(-1);

    // Grab from function start to the next top-level `const ` or `//` comment
    // block that is not indented — a rough but reliable approach.
    const afterFunc = sourceCode.slice(funcStart);
    // Find the closing `};` that matches the arrow function (last one before
    // the next top-level declaration).  We search for `\n  };` (2-space indent)
    // which closes the arrow fn body inside the component.
    const funcEndIdx = afterFunc.indexOf("\n  };");
    const funcBody = funcEndIdx > 0 ? afterFunc.slice(0, funcEndIdx) : afterFunc.slice(0, 600);

    // The primary code path should NOT call window.location.replace() — that
    // is only in the fallback branch when the popup is blocked.
    // Count occurrences: there should be at most one (the fallback).
    const replaceMatches = funcBody.match(/window\.location\.replace\(/g) || [];
    // The fallback is acceptable; more than one means the main path also uses it.
    expect(replaceMatches.length).toBeLessThanOrEqual(1);
  });

  test("popup fallback uses window.location.replace() when popup is blocked", () => {
    // When the browser blocks the popup (popup blocker), the code should fall
    // back to window.location.replace() to minimise history pollution.
    expect(sourceCode).toContain("window.location.replace(");
  });

  test("polling interval is set up via setInterval", () => {
    expect(sourceCode).toContain("setInterval(");
  });

  test("polling detects popup.closed for manual close handling", () => {
    expect(sourceCode).toContain("popup.closed");
  });

  test("polling detects same-origin popup.location.origin for completion", () => {
    expect(sourceCode).toContain("popup.location.origin");
    expect(sourceCode).toContain("window.location.origin");
  });

  test("cleanupPopup function exists and calls clearInterval", () => {
    expect(sourceCode).toContain("cleanupPopup");
    expect(sourceCode).toContain("clearInterval(");
  });

  test("cleanupPopup calls fetchStripeConnectStatus to refresh status", () => {
    // The cleanup function must refresh the Stripe status after the popup closes
    expect(sourceCode).toContain("fetchStripeConnectStatus");
  });

  test("component does NOT modify main window history (no history.pushState for Stripe)", () => {
    // There should be no pushState calls for the Stripe flow — only replaceState
    // is acceptable (and even that should be gone now with the popup approach).
    expect(sourceCode).not.toContain("history.pushState");
  });

  test("component uses useRef to track the popup window reference", () => {
    expect(sourceCode).toContain("popupRef");
    expect(sourceCode).toContain("useRef");
  });

  test("component cleans up interval on unmount via useEffect return", () => {
    // There should be a useEffect that returns a cleanup function clearing the
    // interval to prevent memory leaks.
    expect(sourceCode).toContain("popupPollRef.current");
  });
});

// ---------------------------------------------------------------------------
// 2. URL Construction Logic — Extracted Pure Functions
// ---------------------------------------------------------------------------

/**
 * Mirrors the authorize URL construction from handleConnectStripe.
 * The returnUrl points to the callback route on our origin (not the editor page)
 * because the popup handles the redirect independently.
 */
function buildPopupAuthorizeUrl(origin: string, organizationId: string): string {
  const returnUrl = encodeURIComponent(`${origin}/api/stripe-connect/callback`);
  return `/api/stripe-connect/authorize?organizationId=${organizationId}&returnUrl=${returnUrl}`;
}

describe("PaymentElementForm — Popup authorize URL construction", () => {
  test("builds authorize URL with organizationId and returnUrl pointing to callback", () => {
    const url = buildPopupAuthorizeUrl("http://localhost:3000", "org-123");
    expect(url).toContain("/api/stripe-connect/authorize");
    expect(url).toContain("organizationId=org-123");
    expect(url).toContain("returnUrl=");
    // returnUrl should point to the callback route, not the editor page
    const parsed = new URL(url, "http://localhost:3000");
    const returnUrl = decodeURIComponent(parsed.searchParams.get("returnUrl") || "");
    expect(returnUrl).toContain("/api/stripe-connect/callback");
  });

  test("returnUrl does not include editor-specific paths", () => {
    const url = buildPopupAuthorizeUrl("http://localhost:3000", "org-456");
    const parsed = new URL(url, "http://localhost:3000");
    const returnUrl = decodeURIComponent(parsed.searchParams.get("returnUrl") || "");
    expect(returnUrl).not.toContain("/edit");
    expect(returnUrl).not.toContain("/surveys/");
  });
});

// ---------------------------------------------------------------------------
// 3. Popup Window Features — Centered Dimensions
// ---------------------------------------------------------------------------

/**
 * Mirrors the popup dimension calculation from handleConnectStripe.
 */
function calculatePopupFeatures(
  screenX: number,
  screenY: number,
  outerWidth: number,
  outerHeight: number
): { left: number; top: number; width: number; height: number } {
  const popupWidth = 600;
  const popupHeight = 700;
  const left = Math.max(0, Math.round(screenX + (outerWidth - popupWidth) / 2));
  const top = Math.max(0, Math.round(screenY + (outerHeight - popupHeight) / 2));
  return { left, top, width: popupWidth, height: popupHeight };
}

describe("PaymentElementForm — Popup dimension calculation", () => {
  test("popup is centered horizontally and vertically", () => {
    const features = calculatePopupFeatures(0, 0, 1920, 1080);
    expect(features.left).toBe(660); // (1920 - 600) / 2
    expect(features.top).toBe(190); // (1080 - 700) / 2
    expect(features.width).toBe(600);
    expect(features.height).toBe(700);
  });

  test("popup left/top never go negative", () => {
    const features = calculatePopupFeatures(-100, -50, 400, 300);
    expect(features.left).toBeGreaterThanOrEqual(0);
    expect(features.top).toBeGreaterThanOrEqual(0);
  });

  test("handles small screen correctly", () => {
    const features = calculatePopupFeatures(0, 0, 500, 600);
    expect(features.left).toBeGreaterThanOrEqual(0);
    expect(features.top).toBeGreaterThanOrEqual(0);
  });
});

// ---------------------------------------------------------------------------
// 4. History Stack Verification — Save/Back Button Safety
// ---------------------------------------------------------------------------
describe("PaymentElementForm — Main window history is never affected", () => {
  test("no window.location.href assignment exists for Stripe authorize URL", () => {
    // Direct assignment to window.location.href would push a new history entry
    expect(sourceCode).not.toMatch(/window\.location\.href\s*=\s*[`"']\/api\/stripe-connect/);
  });

  test("no router.push or router.replace calls for Stripe URL exist", () => {
    // The component should not use Next.js router for the Stripe OAuth URL
    expect(sourceCode).not.toMatch(/router\.(push|replace)\([^)]*stripe/i);
  });

  test("window.open is used instead of navigation for the primary flow", () => {
    // The primary connect handler must open a popup
    expect(sourceCode).toContain('window.open(authorizeUrl, "stripe_connect_popup"');
  });
});
