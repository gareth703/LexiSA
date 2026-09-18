import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LexiSA | Convergence3 Contract Intelligence",
  description: "Plain-language contract intelligence for South African SMMEs.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en-ZA"><body>{children}</body></html>;
}
