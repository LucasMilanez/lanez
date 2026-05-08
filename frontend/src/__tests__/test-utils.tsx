/**
 * Test utilities — provider wrappers usados pelos testes que dependem
 * do contexto de i18n, tema e React Query.
 *
 * Os testes devem usar `renderWithProviders` em vez de `render` quando
 * o componente testado utiliza qualquer um desses contextos.
 */
import type { ReactElement, ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "@/i18n/I18nContext";
import { ThemeProvider } from "@/theme/ThemeContext";

interface ProvidersOptions {
  /** Initial route for MemoryRouter (defaults to "/"). */
  route?: string;
  /** Set to false to opt-out of MemoryRouter (e.g. App.tsx already has BrowserRouter). */
  withRouter?: boolean;
  /** Reuse an existing QueryClient (e.g. to pre-seed cache). */
  queryClient?: QueryClient;
}

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

function Providers({
  children,
  route = "/",
  withRouter = true,
  queryClient,
}: ProvidersOptions & { children: ReactNode }) {
  const qc = queryClient ?? makeQueryClient();
  const tree = (
    <ThemeProvider>
      <I18nProvider>
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  );
  return withRouter ? <MemoryRouter initialEntries={[route]}>{tree}</MemoryRouter> : tree;
}

export function renderWithProviders(
  ui: ReactElement,
  options: ProvidersOptions & Omit<RenderOptions, "wrapper"> = {},
) {
  const { route, withRouter, queryClient, ...renderOptions } = options;
  return render(ui, {
    wrapper: ({ children }) => (
      <Providers route={route} withRouter={withRouter} queryClient={queryClient}>
        {children}
      </Providers>
    ),
    ...renderOptions,
  });
}

/**
 * Force a specific locale for a test. Must be called before rendering.
 * Returns a cleanup function — usually unnecessary since each test file
 * runs in a fresh jsdom environment via vitest's isolation.
 */
export function setLocale(locale: "en" | "pt") {
  localStorage.setItem("lanez_locale", locale);
}
