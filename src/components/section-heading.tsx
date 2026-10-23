import type { ReactNode } from "react";

export function SectionHeading({ title, detail }: { title: string; detail?: ReactNode }) {
  return (
    <div className="section-heading-row">
      <h2 className="section-title">{title}</h2>
      {detail ? <span className="section-heading-detail">{detail}</span> : null}
    </div>
  );
}
