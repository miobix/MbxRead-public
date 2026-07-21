import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Korean Reader",
  description: "Read Korean texts, save terms by dictionary form, sync to Anki.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-paper text-ink">
        {children}
      </body>
    </html>
  );
}
