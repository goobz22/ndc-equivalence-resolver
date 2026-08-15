import type { Metadata } from "next";
import { BrowseClient } from "@/components/BrowseClient";

export const metadata: Metadata = {
  title: "Browse & search drug products",
  description:
    "Search US drug products by name, strength, form, manufacturer, or NDC " +
    "fragment — then resolve any product into its FDA-rated interchangeable " +
    "alternatives.",
};

export default function BrowsePage() {
  return <BrowseClient />;
}
