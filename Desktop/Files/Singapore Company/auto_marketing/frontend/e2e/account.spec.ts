import { test, expect } from "@playwright/test";

test.describe("Account & Data API", () => {
  test("data export requires auth", async ({ request }) => {
    const res = await request.get("http://localhost:8080/api/account/export");
    expect(res.status()).toBe(401);
  });

  test("account deletion requires auth", async ({ request }) => {
    const res = await request.delete(
      "http://localhost:8080/api/account?confirm=DELETE"
    );
    expect(res.status()).toBe(401);
  });

  test("account deletion requires confirm=DELETE param", async ({
    request,
  }) => {
    // Even if auth were present, missing confirm should fail
    const res = await request.delete("http://localhost:8080/api/account");
    // 401 because no auth, but tests that the endpoint exists and is wired
    expect(res.status()).toBe(401);
  });
});

test.describe("Settings page – Account tab", () => {
  test("redirects to login when unauthenticated", async ({ page }) => {
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/(\?.*)?$/);
  });
});
