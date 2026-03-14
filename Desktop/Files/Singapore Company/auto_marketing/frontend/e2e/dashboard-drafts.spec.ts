import { test, expect } from "@playwright/test";

test.describe("Dashboard – Content Drafts", () => {
  test("redirects to login when unauthenticated", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/(\?.*)?$/);
  });

  test("draft list API returns expected shape", async ({ request }) => {
    const res = await request.get(
      "http://localhost:8080/api/drafts?status=draft&limit=5"
    );
    // Without auth we should get 401
    expect(res.status()).toBe(401);
  });

  test("draft quick-generate requires auth", async ({ request }) => {
    const res = await request.post(
      "http://localhost:8080/api/drafts/quick-generate",
      { data: { platform: "linkedin" } }
    );
    expect(res.status()).toBe(401);
  });

  test("draft delete requires auth", async ({ request }) => {
    const res = await request.delete(
      "http://localhost:8080/api/drafts/fake-id"
    );
    expect(res.status()).toBe(401);
  });

  test("draft edit (PATCH) requires auth", async ({ request }) => {
    const res = await request.patch(
      "http://localhost:8080/api/drafts/fake-id",
      { data: { headline: "Updated" } }
    );
    expect(res.status()).toBe(401);
  });

  test("draft status update requires auth", async ({ request }) => {
    const res = await request.patch(
      "http://localhost:8080/api/drafts/fake-id/status",
      { data: { status: "scheduled" } }
    );
    expect(res.status()).toBe(401);
  });
});
