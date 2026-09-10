import * as React from "react";
import { cn } from "../utils/cn";

export type CardVariant = "raised" | "muted";

export interface CardProps {
  className?: string;
  variant?: CardVariant;
  children: React.ReactNode;
}

const variants: Record<CardVariant, string> = {
  raised: "rounded-card border border-edge bg-surface p-4 sm:p-6",
  muted: "rounded-card border border-edge bg-surface-muted p-6",
};

const Card = ({ className, variant = "muted", children }: CardProps) => {
  return <div className={cn(variants[variant], className)}>{children}</div>;
};

export { Card };
