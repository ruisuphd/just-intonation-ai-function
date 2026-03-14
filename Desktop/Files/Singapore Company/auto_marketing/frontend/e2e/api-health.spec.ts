import { test, expect } from "@playwright/test";

test.describe("API health", () => {
  test("health endpoint returns ok", async ({ request }) => {
    const res = await request.get("http://localhost:8080/api/health");
    expect(res.ok()).toBeTruthy();

    const body = await res.json();
    expect(body).toMatchObject({ status: "ok" });
  });
});
