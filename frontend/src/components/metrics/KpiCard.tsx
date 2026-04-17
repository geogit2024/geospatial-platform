interface KpiCardProps {
  title: string;
  value: string;
  subtitle?: string;
  tone?: "blue" | "green" | "slate";
}

const toneMap: Record<NonNullable<KpiCardProps["tone"]>, string> = {
  blue: "border-[#1f4369] bg-[#0f2238] text-[#7dd3fc]",
  green: "border-[#1f4f43] bg-[#0f2b24] text-[#6ee7b7]",
  slate: "border-[#24344b] bg-[#101b2c] text-[#d4def0]",
};

export default function KpiCard({ title, value, subtitle, tone = "slate" }: KpiCardProps) {
  return (
    <div className={`rounded-xl border px-4 py-3 shadow-sm ${toneMap[tone]}`}>
      <p className="text-xs uppercase tracking-wide opacity-75">{title}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      {subtitle && <p className="mt-1 text-xs opacity-75">{subtitle}</p>}
    </div>
  );
}
