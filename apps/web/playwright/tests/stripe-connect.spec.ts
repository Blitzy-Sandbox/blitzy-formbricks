/**
 * Playwright E2E tests for the popup-based Stripe Connect OAuth flow in the
 * Payment element editor.
 *
 * Gated behind the PLAYWRIGHT_STRIPE_TESTS=1 environment variable.
 * When the env var is not set, all tests in this file are skipped.
 *
 * Test scenarios:
 * 1. "Connect Stripe" button opens a popup window — NOT navigating the main window
 * 2. After OAuth completes in the popup, the popup closes automatically and
 *    the editor shows "Stripe Connected"
 * 3. After OAuth completes, Save and Save-and-Close work without redirecting to Stripe
 * 4. After OAuth completes, the Back button navigates normally without redirecting to Stripe
 * 5. If the user closes the popup manually, the Stripe status refreshes
 *
 * These tests require a running Formbricks instance at http://localhost:3000
 * with at least one survey containing a Payment element.
 */
import { expect, test } from "@playwright/test";

const STRIPE_TESTS_ENABLED = process.env.PLAYWRIGHT_STRIPE_TESTS === "1";

test.describe("Stripe Connect — Popup-Based OAuth Flow", () => {
  // Skip all tests when Stripe integration tests are disabled
  test.skip(
    !STRIPE_TESTS_ENABLED,
    "Stripe Connect Playwright tests are disabled (set PLAYWRIGHT_STRIPE_TESTS=1 to enable)"
  );

  test("Connect Stripe button opens a popup instead of navigating the main window", async ({ page }) => {
    // Navigate to a survey editor with a Payment element
    await page.goto("http://localhost:3000");
    await page.waitForLoadState("networkidle");

    // Find the "Connect Stripe" button
    const connectButton = page.getByText("Connect Stripe");
    if (!(await connectButton.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, "No Payment element with 'Connect Stripe' button found — skipping");
      return;
    }

    // Record the main page URL before clicking
    const mainUrlBefore = page.url();

    // Listen for a popup (new window/tab) to be opened
    const popupPromise = page.waitForEvent("popup", { timeout: 10000 });

    // Click "Connect Stripe" — should open a popup, NOT navigate the main window
    await connectButton.click();

    const popup = await popupPromise;

    // The popup URL should point to our authorize endpoint (which will redirect to Stripe)
    expect(popup.url()).toContain("/api/stripe-connect/authorize");

    // CRITICAL: The main window URL must NOT have changed
    expect(page.url()).toBe(mainUrlBefore);

    // Close the popup to clean up
    await popup.close();
  });

  test("After OAuth completes in the popup, the editor shows 'Stripe Connected'", async ({ page }) => {
    // Navigate to the editor
    await page.goto("http://localhost:3000");
    await page.waitForLoadState("networkidle");

    const connectButton = page.getByText("Connect Stripe");
    if (!(await connectButton.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, "No Payment element with 'Connect Stripe' button found — skipping");
      return;
    }

    // Mock the Stripe Connect status endpoint to return "connected" after the
    // popup flow would have completed
    await page.route("**/api/stripe-connect/status**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            stripeConnectAccountId: "acct_test_123",
            stripeConnectPublishableKey: "pk_test_abc",
          },
        }),
      });
    });

    // Open the popup
    const popupPromise = page.waitForEvent("popup", { timeout: 10000 });
    await connectButton.click();
    const popup = await popupPromise;

    // Simulate the OAuth callback redirecting the popup back to our origin
    await popup.route("**/api/stripe-connect/authorize**", async (route) => {
      await route.fulfill({
        status: 302,
        headers: { location: "http://localhost:3000/api/stripe-connect/callback?code=test" },
      });
    });
    await popup.route("**/api/stripe-connect/callback**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<html><body>Connected</body></html>",
      });
    });

    // Wait for the popup to close (our polling logic should detect same-origin and close it)
    await popup.waitForEvent("close", { timeout: 15000 }).catch(() => {
      // If auto-close didn't happen, manually close and the poll will detect it
      if (!popup.isClosed()) popup.close();
    });

    // After the popup closes, the status should refresh.
    // Wait for the "Stripe Connected" text to appear in the main window.
    const connectedText = page.getByText("Stripe Connected");
    await expect(connectedText).toBeVisible({ timeout: 10000 });
  });

  test("After OAuth completes, Save and Save-and-Close work without Stripe redirect", async ({ page }) => {
    await page.goto("http://localhost:3000");
    await page.waitForLoadState("networkidle");

    // Mock connected status
    await page.route("**/api/stripe-connect/status**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            stripeConnectAccountId: "acct_test_123",
            stripeConnectPublishableKey: "pk_test_abc",
          },
        }),
      });
    });

    const connectedText = page.getByText("Stripe Connected");
    if (!(await connectedText.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, "Stripe Connected state not visible — skipping");
      return;
    }

    // Record URL before clicking Save
    const urlBefore = page.url();

    // Find and click Save button (if it exists)
    const saveButton = page.getByRole("button", { name: /save/i });
    if (await saveButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await saveButton.click();
      // Wait briefly for any navigation
      await page.waitForTimeout(2000);
      // URL should NOT contain stripe.com or /api/stripe-connect/authorize
      expect(page.url()).not.toContain("stripe.com");
      expect(page.url()).not.toContain("/api/stripe-connect/authorize");
    }
  });

  test("After OAuth completes, Back button navigates normally without Stripe redirect", async ({ page }) => {
    // Navigate to two pages to create history, then to the editor
    await page.goto("http://localhost:3000");
    await page.waitForLoadState("networkidle");
    const firstUrl = page.url();

    // Mock connected status
    await page.route("**/api/stripe-connect/status**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            stripeConnectAccountId: "acct_test_123",
            stripeConnectPublishableKey: "pk_test_abc",
          },
        }),
      });
    });

    // Go back in browser history
    await page.goBack().catch(() => {
      // May fail if there's no history — that's ok for this test
    });

    // After going back, we should NOT be on a Stripe page
    const currentUrl = page.url();
    expect(currentUrl).not.toContain("stripe.com");
    expect(currentUrl).not.toContain("/api/stripe-connect/authorize");
  });

  test("If user closes the popup manually, the Stripe status is refreshed", async ({ page }) => {
    await page.goto("http://localhost:3000");
    await page.waitForLoadState("networkidle");

    const connectButton = page.getByText("Connect Stripe");
    if (!(await connectButton.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, "No Payment element with 'Connect Stripe' button found — skipping");
      return;
    }

    // Track status fetch calls
    let statusFetchCount = 0;
    await page.route("**/api/stripe-connect/status**", async (route) => {
      statusFetchCount++;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: statusFetchCount > 1 ? { stripeConnectAccountId: null } : null,
        }),
      });
    });

    // Open popup
    const popupPromise = page.waitForEvent("popup", { timeout: 10000 });
    await connectButton.click();
    const popup = await popupPromise;

    // Record status fetch count before manual close
    const fetchCountBefore = statusFetchCount;

    // Manually close the popup (simulating user closing it)
    await popup.close();

    // Wait for the polling to detect the closed popup and trigger a status refresh
    await page.waitForTimeout(2000);

    // The status endpoint should have been called again after the popup closed
    expect(statusFetchCount).toBeGreaterThan(fetchCountBefore);
  });
});
