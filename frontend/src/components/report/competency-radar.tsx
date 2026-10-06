"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Text,
  Tooltip,
} from "recharts";
import type { CompetencyScore } from "@intervyn/shared";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

const ACCENT = "var(--color-accent)";
const LINE = "var(--color-line)";
const MUTED = "var(--color-muted)";

/**
 * Calm radar of competency scores on a fixed 0-5 domain. Client island —
 * recharts needs the DOM. The parent passes plain serializable
 * `competency_scores`; we map to recharts' row shape here.
 *
 * ResponsiveContainer collapses to 0 inside auto-height parents, so the wrapper
 * has an explicit height.
 */
export function CompetencyRadar({
  competencies,
}: {
  competencies: CompetencyScore[];
}) {
  const messages = useMessages();
  const data = competencies.map((c) => ({
    competency: c.competency,
    score: c.score,
  }));

  return (
    <div className="h-[300px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart
          data={data}
          outerRadius="56%"
          margin={{ top: 24, right: 32, bottom: 24, left: 32 }}
          accessibilityLayer={false}
        >
          <PolarGrid stroke={LINE} />
          <PolarAngleAxis
            dataKey="competency"
            tick={({ x, y, payload, textAnchor }) => (
              <Text
                x={
                  Number(x) +
                  (textAnchor === "start" ? 24 : textAnchor === "end" ? -24 : 0)
                }
                y={y}
                width={textAnchor === "middle" ? 90 : 70}
                textAnchor="middle"
                verticalAnchor="middle"
                style={{ fill: MUTED, fontSize: 11 }}
              >
                {String(payload.value)}
              </Text>
            )}
          />
          <PolarRadiusAxis
            domain={[0, 5]}
            tickCount={6}
            tick={{ fill: "var(--color-faint)", fontSize: 10 }}
            axisLine={false}
          />
          <Radar
            name={t(messages, "report.scoreLabel")}
            dataKey="score"
            stroke={ACCENT}
            fill={ACCENT}
            fillOpacity={0.14}
            strokeWidth={2}
            dot={{ r: 2.5, fill: ACCENT, strokeWidth: 0 }}
          />
          <Tooltip
            formatter={(value) => [
              `${value} / 5`,
              t(messages, "report.scoreLabel"),
            ]}
            contentStyle={{
              backgroundColor: "var(--color-panel)",
              color: "var(--color-ink)",
              borderRadius: 10,
              border: `1px solid ${LINE}`,
              fontSize: 12,
              boxShadow: "0 8px 24px #0005",
            }}
            itemStyle={{ color: "var(--color-accent)" }}
            labelStyle={{ color: "var(--color-ink)", fontWeight: 600 }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
