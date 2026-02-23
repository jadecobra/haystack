import * as React from "react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer } from "recharts";

export interface SparklineProps {
  data: { name: string; value: number }[];
  color?: string;
}

const Sparkline = ({ data, color = "#10b981" }: SparklineProps) => {
  return (
    <ResponsiveContainer width="100%" height={40}>
      <LineChart data={data}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={false}
        />
        <XAxis
          dataKey="name"
          axisLine={false}
          tickLine={false}
          tick={{ fill: "#9ca3af" }}
        />
        <YAxis
          axisLine={false}
          tickLine={false}
          tick={{ fill: "#9ca3af" }}
          width={30}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};

export { Sparkline };
