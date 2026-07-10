import type { Metadata } from 'next'
import '../index.css'
import '../app-shell/App.css'

import SessionGuard from '@/features/auth/SessionGuard'

export const metadata: Metadata = {
  title: 'Maily',
  description: '여러 Gmail 계정의 중요한 메일을 선별해 브리핑하는 웹 서비스',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&display=swap"
          rel="stylesheet"
        />
        <link
          rel="stylesheet"
          as="style"
          crossOrigin="anonymous"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css"
        />
      </head>
      <body>
        <SessionGuard>{children}</SessionGuard>
      </body>
    </html>
  )
}
