"use client";

import { Star, Terminal } from "lucide-react";

const COLORS = {
  light: {
    bg: "#ffffff",
    text: "#1a1a1a",
    textMuted: "#666666",
    border: "#e5e5e5",
  },
  dark: {
    bg: "#0b0214",
    text: "#ffffff",
    textMuted: "#b996d6",
    border: "#2a0d40",
  },
} as const;

const FOOTER_LINKS = [
  { label: "Source on GitHub", href: "https://github.com/ethembeldagli/termwrapped" },
  { label: "roastfetch", href: "https://github.com/ethembeldagli/roastfetch" },
  { label: "Millennium for Bazzite", href: "https://github.com/ethembeldagli/millennium-bazzite" },
  { label: "MIT licence · runs offline", href: "#install" },
];

interface LoopsSoFooter6Props {
  mode?: "light" | "dark";
}

export default function LoopsSoFooter6({
  mode = "light",
}: LoopsSoFooter6Props) {
  const colors = COLORS[mode];

  return (
    <footer
      className="w-full py-8"
      style={{
        backgroundColor: colors.bg,
        borderTop: `1px solid ${colors.border}`,
      }}
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Logo and Links */}
          <div className="flex flex-col md:flex-row items-center gap-4 md:gap-8">
            {/* Logo */}
            <a href="https://github.com/ethembeldagli/termwrapped" className="flex items-center gap-2">
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center"
                style={{ backgroundColor: "#ff5fd2" }}
              >
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <circle cx="12" cy="12" r="8" stroke="white" strokeWidth="3" fill="none" />
                </svg>
              </div>
            </a>

            {/* Links */}
            <nav className="flex flex-wrap items-center justify-center gap-4 md:gap-6">
              {FOOTER_LINKS.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  className="text-sm transition-colors hover:opacity-80"
                  style={{ color: colors.textMuted }}
                >
                  {link.label}
                </a>
              ))}
            </nav>
          </div>

          {/* Right Side */}
          <div className="flex items-center gap-4">
            {/* Social Icons */}
            <div className="flex items-center gap-3">
              <a
                href="https://github.com/ethembeldagli/termwrapped"
                className="transition-colors hover:opacity-80"
                style={{ color: colors.textMuted }}
              >
                <Star className="w-4 h-4" />
              </a>
              <a
                href="#install"
                className="transition-colors hover:opacity-80"
                style={{ color: colors.textMuted }}
              >
                <Terminal className="w-4 h-4" />
              </a>
            </div>

            {/* Y Combinator Badge */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-orange-50">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <rect width="24" height="24" rx="4" fill="#FF6600" />
                <path
                  d="M7 7L12 14V17H12V14L17 7H14.5L12 11.5L9.5 7H7Z"
                  fill="white"
                />
              </svg>
              <span className="text-xs font-medium text-orange-600">
                Backed by Y Combinator
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
