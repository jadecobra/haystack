import * as React from "react";
import { cn } from "../utils/cn";

export type DataTableGroupRow = {
  kind: "group";
  title: string;
};

export type DataTableDataRow = {
  kind: "data";
  cells: React.ReactNode[];
};

export type DataTableRow = DataTableGroupRow | DataTableDataRow | React.ReactNode[];

export interface DataTableProps {
  className?: string;
  framed?: boolean;
  headers: string[];
  rows: DataTableRow[];
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
            if (!Array.isArray(row) && row.kind === "group") {
              const isFirstGroup = !rows
                .slice(0, rowIndex)
                .some((r) => !Array.isArray(r) && r.kind === "group");
              return (
                <tr key={`group-${rowIndex}`} className="bg-surface">
                  <th
                    colSpan={Math.max(headers.length, 1)}
                    scope="colgroup"
                    className={cn(
                      "text-left py-3 sm:py-4 px-2 font-semibold text-zinc-100 sticky left-0 z-10 bg-surface border-t-2 border-zinc-600",
                      !isFirstGroup && "pt-5 sm:pt-6"
                    )}
                  >
                    {row.title}
                  </th>
                </tr>
              );
            }
            const cells = Array.isArray(row) ? row : row.cells;
            const dataIndex = rows
              .slice(0, rowIndex)
              .filter((r) => Array.isArray(r) || (!Array.isArray(r) && r.kind === "data"))
              .length;
            const stripe = dataIndex % 2 === 0 ? "bg-canvas" : "bg-surface";
            return (
              <tr key={rowIndex} className={stripe}>
                {cells.map((cell, cellIndex) => (
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
