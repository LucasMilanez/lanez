import { describe, it, expect, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";
import { ThemeProvider, useTheme } from "@/theme/ThemeContext";

function TestConsumer() {
  const { setTheme, resolvedTheme } = useTheme();
  return (
    <div>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setTheme("dark")}>Set Dark</button>
      <button onClick={() => setTheme("light")}>Set Light</button>
    </div>
  );
}

beforeEach(() => {
  document.documentElement.classList.remove("light", "dark");
  localStorage.clear();
});

describe("ThemeContext", () => {
  it("setTheme('dark') adds class 'dark' to document.documentElement and persists in localStorage", () => {
    const { getByText } = render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    );

    act(() => {
      getByText("Set Dark").click();
    });

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("lanez_theme")).toBe("dark");
  });
});
