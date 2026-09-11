import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'Legal Advisor — Indian Legal Information & Advocate Connect',
    template: '%s · Legal Advisor',
  },
  description:
    'AI-powered Indian legal information, document guidance and advocate discovery. Not legal advice.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
