import { test, expect } from "@playwright/test";

test.describe("Newsletter API", () => {
  test("list newsletters requires auth", async ({ request }) => {
    const res = await request.get("http://localhost:8080/api/newsletters");
    expect(res.status()).toBe(401);
  });

  test("generate newsletter requires auth", async ({ request }) => {
    const res = await request.post(
      "http://localhost:8080/api/newsletters/generate"
    );
    expect(res.status()).toBe(401);
  });

  test("schedule newsletter requires auth", async ({ request }) => {
    const res = await request.post(
      "http://localhost:8080/api/newsletters/schedule",
      {
        data: {
          newsletter_id: "fake-id",
          scheduled_at: "2026-04-01T09:00:00Z",
          platform: "ghost",
        },
      }
    );
    expect(res.status()).toBe(401);
  });
});
