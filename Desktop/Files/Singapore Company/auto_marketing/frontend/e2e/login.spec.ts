import { test, expect } from "@playwright/test";

test.describe("Login page", () => {
  test("loads with AutoMark branding and sign-in options", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "AutoMark" })).toBeVisible();
    await expect(page.getByText("AI-powered marketing for your business.")).toBeVisible();
    await expect(page.getByRole("button", { name: /Continue with Google/i })).toBeVisible();
  });

  test("shows email option when clicking Continue with Email", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: /Continue with Email/i }).click();

    await expect(page.getByPlaceholder("Email address")).toBeVisible();
    await expect(page.getByPlaceholder("Password")).toBeVisible();
  });
});
