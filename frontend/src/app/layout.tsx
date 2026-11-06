import type { Metadata } from "next";
import "./globals.css";
import AppProvider from "@/components/AppProvider";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "Post Scheduler",
  description: "Plan, write and schedule SEO-friendly LinkedIn and Instagram posts.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppProvider>
          <Shell>{children}</Shell>
        </AppProvider>
      </body>
    </html>
  );
}
