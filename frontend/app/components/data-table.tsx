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
        "rounded-lg border bg-background p-6 shadow-sm ring-1 ring-inset ring-background/50 overflow-x-auto",
        className
      )}
    >
      <table className="w-full">
        <thead>
          <tr className="border-b">
            {headers.map((header, index) => (
              <th
                key={index}
                className="text-left py-3 font-semibold text-zinc-400"
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
                <td key={cellIndex} className="py-3 px-2 text-zinc-300">
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
