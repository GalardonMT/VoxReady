import type { Metadata } from 'next';
import './globals.css';
import { ThemeProvider } from '../context/ThemeContext';
import { I18nProvider } from '../context/I18nContext';
import { AuthProvider } from '../context/AuthContext';
import { MsalWrapper } from '../components/auth/MsalWrapper';

export const metadata: Metadata = {
  title: 'VoxReady — Plataforma de Entrenamiento en Vocería de Crisis',
  description: 'Autoaprendizaje y evaluación multimodal con IA (voz, imagen y contenido) para voceros organizacionales. Desarrollado con Visum.',
  icons: {
    icon: '/favicon.ico'
  }
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>
        <ThemeProvider>
          <I18nProvider>
            <MsalWrapper>
              <AuthProvider>
                {children}
              </AuthProvider>
            </MsalWrapper>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
