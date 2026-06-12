import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KnowledgeBot — AI-Powered Knowledge Assistant",
  description:
    "Upload documents, paste URLs, and ask questions. KnowledgeBot answers from your content with source citations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
