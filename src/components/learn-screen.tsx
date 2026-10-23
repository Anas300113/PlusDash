import Link from "next/link";
import { ArrowRight, LockKeyhole, Shapes } from "lucide-react";
import { MasteryBar } from "@/components/progress-indicators";
import { subjects } from "@/lib/data";

export function LearnScreen() {
  return (
    <div className="page-stack learn-page">
      <section className="page-intro" aria-labelledby="learn-title">
        <h1 id="learn-title" className="page-title">What shall we <span className="highlight-underline">learn</span>?</h1>
        <p>Pick a subject, then a topic.</p>
      </section>

      <section aria-label="Choose a subject">
        <div className="subject-grid">
          {subjects.map(({ id, name, mastery, topicCount, icon: Icon }) => (
            <Link href={`/learn/${id}`} className="subject-card" key={id}>
              <span className="subject-icon"><Icon size={21} strokeWidth={2} aria-hidden="true" /></span>
              <span className="subject-name">{name}</span>
              <MasteryBar value={mastery} label={`${name} mastery`} />
              <span className="subject-meta"><strong>{mastery}% mastered</strong><span>{topicCount} topics</span></span>
              <span className="subject-card-arrow"><ArrowRight size={17} aria-hidden="true" /></span>
            </Link>
          ))}
        </div>
      </section>

      <section className="wobbly-section" aria-labelledby="wobbly-heading">
        <div className="section-heading-row">
          <h2 id="wobbly-heading" className="section-title">Pick up where it’s wobbly</h2>
          <span className="quiet-label">A little review can help</span>
        </div>
        <Link className="wobbly-card" href="/practice?subject=non-verbal-reasoning&topic=rotations">
          <span className="wobbly-icon"><Shapes size={21} strokeWidth={2} aria-hidden="true" /></span>
          <span className="wobbly-copy">
            <strong>Non-verbal: rotations</strong>
            <span>3 of the last 5 answers missed</span>
          </span>
          <span className="button button-dark button-compact">Try <ArrowRight size={16} aria-hidden="true" /></span>
        </Link>
      </section>

      <section className="locked-card" aria-label="Timed mock paper locked">
        <span className="locked-icon"><LockKeyhole size={19} strokeWidth={2} aria-hidden="true" /></span>
        <span className="locked-copy">
          <strong>Timed mock paper</strong>
          <span>Unlocks after 5 more topics</span>
        </span>
        <span className="locked-status">Locked</span>
      </section>
    </div>
  );
}
