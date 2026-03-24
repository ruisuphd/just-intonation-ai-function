import { test, expect } from "@playwright/test";

test.describe("Marketing home", () => {
  test("shows hero and CTAs to sign up", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Your AI marketing team/i })).toBeVisible();
    await expect(page.getByRole("link", { name: "Get started free" }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Sign in" }).first()).toBeVisible();
  });
});

test.describe("Login page", () => {
  test("loads with IntoMarketing branding and sign-in options", async ({ page }) => {
    await page.goto("/login");

    await expect(page.getByText("IntoMarketing").first()).toBeVisible();
    await expect(page.getByText("Your AI marketing team, working while you sleep.")).toBeVisible();
    await expect(page.getByRole("button", { name: /Continue with Google/i })).toBeVisible();
    await expect(page.getByPlaceholder("you@company.com")).toBeVisible();
    await expect(page.getByPlaceholder("••••••••")).toBeVisible();
  });

  test("shows inline email sign-in form", async ({ page }) => {
    await page.goto("/login");

    await expect(page.getByPlaceholder("you@company.com")).toBeVisible();
    await expect(page.getByPlaceholder("••••••••")).toBeVisible();
    await expect(page.getByRole("button", { name: /Sign in|Create account/i })).toBeVisible();
  });
});
