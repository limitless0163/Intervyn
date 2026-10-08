"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const messages = useMessages();
  const isDark = theme === "dark";
  const label = t(
    messages,
    isDark ? "common.switchToLight" : "common.switchToDark",
  );

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={label}
      title={label}
      onClick={toggleTheme}
    >
      {isDark ? <Sun size={17} aria-hidden /> : <Moon size={17} aria-hidden />}
      <span>
        {t(messages, isDark ? "common.lightTheme" : "common.darkTheme")}
      </span>
    </button>
  );
}
