import * as React from "react";
import { cn } from "../utils/cn";

export type ButtonProps = React.ComponentProps<"button">;

const buttonClass =
  "w-full sm:w-auto bg-accent hover:bg-zinc-100 text-accent-fg px-6 sm:px-12 py-3.5 sm:py-5 rounded-2xl sm:rounded-3xl font-semibold text-base sm:text-xl transition-all disabled:opacity-50 flex items-center justify-center sm:min-w-[160px] shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-edge-focus/40 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas";

const Button = ({ className, type = "button", ...props }: ButtonProps) => {
  return (
    <button type={type} className={cn(buttonClass, className)} {...props} />
  );
};

export { Button };
