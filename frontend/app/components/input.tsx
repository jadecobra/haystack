import * as React from "react";
import { cn } from "../utils/cn";

export type InputProps = React.ComponentProps<"input">;

const inputClass =
  "w-full sm:flex-1 min-w-0 bg-surface border border-edge-strong rounded-2xl sm:rounded-3xl px-4 sm:px-8 py-3.5 sm:py-5 text-lg sm:text-2xl text-foreground placeholder:text-muted-2 focus:outline-none focus:border-edge-focus focus-visible:ring-2 focus-visible:ring-edge-focus/40 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas";

const Input = ({ className, type = "text", ...props }: InputProps) => {
  return <input type={type} className={cn(inputClass, className)} {...props} />;
};

export { Input };
