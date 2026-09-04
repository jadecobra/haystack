import * as React from "react";
import { cn } from "../utils/cn";

export interface DataTableProps {
  className?: string;
  headers: string[];
  rows: string[][];
}

const DataTable = ({ className, headers, rows }: DataTableProps) => {
  return (
    <div
      className={cn(
        "rounded-lg border bg-background p-3 sm:p-6 shadow-sm ring-1 ring-inset ring-background/50 overflow-x-auto -mx-1 sm:mx-0",
        className
      )}
    >
      <table className="w-full min-w-[36rem] text-sm sm:text-base">
        <thead>
          <tr className="border-b">
            {headers.map((header, index) => (
              <th
                key={index}
                className={cn(
                  "text-left py-2 sm:py-3 px-2 font-semibold text-zinc-400 whitespace-nowrap",
                  index === 0 && "sticky left-0 bg-zinc-950 z-10"
                )}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className={rowIndex % 2 === 0 ? "bg-zinc-950" : "bg-zinc-900"}
            >
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className={cn(
                    "py-2 sm:py-3 px-2 text-zinc-300 whitespace-nowrap",
                    cellIndex === 0 &&
                      (rowIndex % 2 === 0
                        ? "sticky left-0 bg-zinc-950 z-10"
                        : "sticky left-0 bg-zinc-900 z-10")
                  )}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export { DataTable };
