import { test, expect } from "@playwright/test";

test.describe("Onboarding page", () => {
  test("redirects to login when unauthenticated", async ({ page }) => {
    await page.goto("/onboarding");

    await expect(page).toHaveURL(/\/(\?.*)?$/);
    await expect(page.getByText("IntoMarketing").first()).toBeVisible();
  });
});
