import * as React from "react";
import { cn } from "../utils/cn";

export interface DataTableProps {
  className?: string;
  framed?: boolean;
  headers: string[];
  rows: React.ReactNode[][];
}

const DataTable = ({
  className,
  framed = false,
  headers,
  rows,
}: DataTableProps) => {
  // Match wrapper when framed; otherwise even-row stripe (first body row).
  const headerBg = framed ? "bg-surface" : "bg-canvas";

  return (
    <div
      className={cn(
        framed
          ? "rounded-card border border-edge bg-surface overflow-x-auto p-3 sm:p-6"
          : "overflow-x-auto",
        className
      )}
    >
      <table className="w-full min-w-[36rem] text-sm sm:text-base">
        <thead>
          <tr className="border-b border-edge">
            {headers.map((header, index) => (
              <th
                key={index}
                className={cn(
                  "text-left py-2 sm:py-3 px-2 font-semibold text-zinc-400 whitespace-nowrap",
                  headerBg,
                  index === 0 && "sticky left-0 z-10"
                )}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => {
            const stripe = rowIndex % 2 === 0 ? "bg-canvas" : "bg-surface";
            return (
              <tr key={rowIndex} className={stripe}>
                {row.map((cell, cellIndex) => (
                  <td
                    key={cellIndex}
                    className={cn(
                      "py-2 sm:py-3 px-2 text-zinc-300",
                      cellIndex === 0
                        ? "whitespace-normal max-w-[16rem] sm:max-w-xs"
                        : "whitespace-nowrap",
                      cellIndex === 0 && `sticky left-0 z-10 ${stripe}`
                    )}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export { DataTable };
