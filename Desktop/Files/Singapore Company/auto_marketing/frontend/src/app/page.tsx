import type { Metadata } from "next";
import { getSiteUrl } from "@/lib/site-url";
import HomePageClient from "./home-page-client";

export const metadata: Metadata = {
  alternates: {
    canonical: "/",
  },
  openGraph: {
    url: getSiteUrl(),
  },
};

export default function HomePage() {
  return <HomePageClient />;
}
