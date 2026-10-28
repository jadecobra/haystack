import * as React from "react";
import { docsNavLink, oeComparisonLinks } from "@/lib/siteNav";
import { cn } from "../utils/cn";
import { TextLink } from "./text-link";

export interface PageShellProps {
  children: React.ReactNode;
  maxWidth?: "wide" | "prose";
  centerViewport?: boolean;
  textAlign?: "center" | "start";
  className?: string;
}

const maxWidthClass = {
  wide: "max-w-7xl",
  prose: "max-w-3xl",
} as const;

const textAlignClass = {
  center: "text-center",
  start: "text-left",
} as const;

const PageShell = ({
  children,
  maxWidth = "wide",
  centerViewport = false,
  textAlign = "start",
  className,
}: PageShellProps) => {
  return (
    <main
      className={cn(
        "min-h-dvh bg-canvas text-foreground overflow-x-hidden",
        centerViewport && "flex items-center justify-center",
      )}
    >
      <div
        className={cn(
          "w-full mx-auto px-4 sm:px-6",
          maxWidthClass[maxWidth],
          centerViewport ? "py-8 sm:py-16" : "py-10 sm:py-16",
          textAlignClass[textAlign],
          className,
        )}
      >
        {children}
        <nav
          aria-label="Site navigation"
          data-testid="site-nav"
          className="mt-8 sm:mt-10 text-muted-2 text-sm sm:text-base px-1 space-y-2"
        >
          <p>
            <TextLink href={docsNavLink().href}>{docsNavLink().label}</TextLink>
          </p>
          <p>
            OE Comparison:{" "}
            {oeComparisonLinks().map((link, index) => (
              <React.Fragment key={link.href}>
                {index > 0 ? " · " : null}
                <TextLink href={link.href}>{link.label}</TextLink>
              </React.Fragment>
            ))}
          </p>
        </nav>
        <p className="mt-3 text-muted-2 text-sm sm:text-base px-1">
          © 2026 JadeCobra LLC
        </p>
      </div>
    </main>
  );
};

export { PageShell };
