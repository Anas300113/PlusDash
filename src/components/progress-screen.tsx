import Link from "next/link";
import { ArrowRight, Check, Clock3 } from "lucide-react";
import { MasteryBar } from "@/components/progress-indicators";
import { subjects, weekDays } from "@/lib/data";

const activityMinutes = [12, 18, 9, 15, 18, 0, 0];

export function ProgressScreen() {
  const overall = Math.round(subjects.reduce((total, subject) => total + subject.mastery, 0) / subjects.length);

  return (
    <div className="page-stack progress-page">
      <section className="page-intro" aria-labelledby="progress-title">
        <h1 id="progress-title" className="page-title">Look how far you’ve come</h1>
        <p>Every bit of practice helps you grow.</p>
      </section>

      <section className="progress-overview" aria-labelledby="mastery-heading">
        <div className="progress-overview-head">
          <div>
            <h2 id="mastery-heading" className="section-title">Topics you’ve mastered</h2>
            <p>Across the subjects you’re learning</p>
          </div>
          <span className="overall-stat"><strong>{overall}%</strong><span>overall</span></span>
        </div>
        <div className="progress-subject-list">
          {subjects.map(({ id, name, mastery }) => (
            <Link className="progress-subject-row" href={`/learn/${id}`} key={id}>
              <span className="progress-subject-name">{name}</span>
              <MasteryBar value={mastery} label={`${name} mastery`} />
              <span className="progress-subject-value">{mastery}%</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="activity-section" aria-labelledby="activity-heading">
        <div className="section-heading-row">
          <h2 id="activity-heading" className="section-title">Your practice this week</h2>
          <span className="week-note"><Clock3 size={15} aria-hidden="true" /> Minutes practised</span>
        </div>
        <div className="activity-chart" role="list" aria-label="Minutes practised each day this week">
          {weekDays.map(({ label, state }, index) => (
            <div className="activity-day" role="listitem" key={label} aria-label={`${label}: ${activityMinutes[index]} minutes`}>
              <span className="activity-value">{activityMinutes[index] ? `${activityMinutes[index]}m` : "—"}</span>
              <span className="activity-bar-track" aria-hidden="true"><span className={`activity-bar-fill${state === "today" ? " activity-today" : ""}`} style={{ height: `${Math.max(activityMinutes[index] / 18 * 100, 5)}%` }} /></span>
              <span className="activity-label">{label}</span>
            </div>
          ))}
        </div>
        <p className="activity-caption"><span className="tiny-check"><Check size={13} strokeWidth={2.5} aria-hidden="true" /></span> You’ve practised on 5 days this week.</p>
      </section>

      <Link href="/practice?subject=non-verbal-reasoning&topic=rotations" className="next-step-card">
        <span className="next-step-copy"><span className="next-step-label">A good next step</span><strong>Give rotations another try</strong><span>Short practice can make tricky topics feel clearer.</span></span>
        <span className="next-step-arrow" aria-hidden="true"><ArrowRight size={20} /></span>
      </Link>
    </div>
  );
}
