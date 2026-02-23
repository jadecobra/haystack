import * as React from "react";
import { cn } from "../utils/cn";

export interface CardProps {
  className?: string;
  children: React.ReactNode;
}

const Card = ({ className, children }: CardProps) => {
  return (
    <div
      className={cn(
        "rounded-lg border bg-background p-6 shadow-sm ring-1 ring-inset ring-background/50 transition-all duration-200 hover:shadow-md",
        className
      )}
    >
      {children}
    </div>
  );
};

export { Card };
