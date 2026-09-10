import * as React from "react";
import Link from "next/link";
import { cn } from "../utils/cn";

export type TextLinkProps = React.ComponentProps<typeof Link>;

const textLinkClass =
  "underline underline-offset-4 text-muted-2 hover:text-zinc-300";

const TextLink = ({ className, ...props }: TextLinkProps) => {
  return <Link className={cn(textLinkClass, className)} {...props} />;
};

export { TextLink };
