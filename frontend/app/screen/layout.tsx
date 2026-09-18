import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "S&P 500 OE-yield screen - LongMuch",
  description:
    "Daily S&P 500 screen of trailing owner earnings per share divided by prior close.",
};

export default function ScreenLayout({
  children,
}: {
  children: ReactNode;
}) {
  return children;
}
