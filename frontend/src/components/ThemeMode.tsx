import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeMode = "light" | "dark";

interface ThemeModeValue {
  themeMode: ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
  toggleThemeMode: () => void;
}

const THEME_STORAGE_KEY = "xona-theme";

const ThemeModeContext = createContext<ThemeModeValue>({
  themeMode: "dark",
  setThemeMode: () => undefined,
  toggleThemeMode: () => undefined,
});

export function ThemeModeProvider({ children }: { children: ReactNode }) {
  const [themeMode, setThemeModeState] = useState<ThemeMode>(resolveInitialTheme);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, themeMode);
    } catch {
      // Theme persistence is optional; the selected mode still applies in memory.
    }
  }, [themeMode]);

  const value = useMemo<ThemeModeValue>(
    () => ({
      themeMode,
      setThemeMode: setThemeModeState,
      toggleThemeMode: () =>
        setThemeModeState((current) => (current === "dark" ? "light" : "dark")),
    }),
    [themeMode],
  );

  return (
    <ThemeModeContext.Provider value={value}>
      {children}
    </ThemeModeContext.Provider>
  );
}

export function useThemeMode() {
  return useContext(ThemeModeContext);
}

function resolveInitialTheme(): ThemeMode {
  const storedMode = readStoredThemeMode();
  if (storedMode) {
    return storedMode;
  }
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    if (window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
  }
  return "dark";
}

function readStoredThemeMode(): ThemeMode | null {
  try {
    const storedMode = localStorage.getItem(THEME_STORAGE_KEY);
    return storedMode === "light" || storedMode === "dark" ? storedMode : null;
  } catch {
    return null;
  }
}
