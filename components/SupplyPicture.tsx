import { ClassAssessment, SourceRefs } from "@/lib/api";
import { SourceTag } from "@/components/SourceTag";

const VERDICT_STYLE: Record<string, { className: string; label: string }> = {
  "fda-listed-shortage": {
    className: "verdict t3",
    label: "CONFIRMED SHORTAGE (FDA list)",
  },
  "evidence-consistent-with-supply-constraint": {
    className: "verdict t3",
    label: "SUPPLY CONSTRAINT LIKELY (independent public evidence)",
  },
  "mixed-signals": { className: "verdict t4", label: "MIXED SIGNALS" },
  "no-independent-stress-evidence": {
    className: "verdict t1",
    label: "NO INDEPENDENT STRESS EVIDENCE",
  },
};

export function SupplyPicture({
  assessment,
  refs,
}: {
  assessment: ClassAssessment;
  refs?: SourceRefs;
}) {
  const style =
    VERDICT_STYLE[assessment.verdict] ?? VERDICT_STYLE["mixed-signals"];
  return (
    <div className={style.className}>
      <b>Supply picture — {style.label}</b>
      <p style={{ margin: "0.4rem 0 0.6rem" }}>{assessment.verdict_language}</p>
      <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.88rem" }}>
        {assessment.lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <SourceTag
        refs={refs}
        ids={["shortage", "nadac", "sdud", "enforcement"]}
      />
    </div>
  );
}
