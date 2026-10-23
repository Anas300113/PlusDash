"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ArrowRight, Clock3 } from "lucide-react";
import { MasteryBar } from "@/components/progress-indicators";
import { subjects } from "@/lib/data";

export function SubjectTopics() {
  const params = useParams<{ subject: string }>();
  const subject = subjects.find((item) => item.id === params.subject);

  if (!subject) {
    return (
      <section className="page-stack not-found-card">
        <h1 className="page-title">Let’s find that subject</h1>
        <p>That subject isn’t here yet. Choose from the subjects you can practise.</p>
        <Link className="button button-primary" href="/learn"><ArrowLeft size={17} /> Back to Learn</Link>
      </section>
    );
  }

  const Icon = subject.icon;

  return (
    <div className="page-stack topic-page">
      <Link className="back-link" href="/learn"><ArrowLeft size={17} aria-hidden="true" /> All subjects</Link>
      <section className="topic-intro">
        <span className="subject-icon subject-icon-large"><Icon size={24} strokeWidth={2} aria-hidden="true" /></span>
        <div>
          <h1 className="page-title">{subject.name}</h1>
          <p>Pick a topic for a short practice.</p>
        </div>
      </section>

      <section className="topic-overview" aria-label={`${subject.name} mastery`}>
        <div className="topic-overview-copy"><strong>{subject.mastery}% mastered</strong><span>{subject.topicCount} topics</span></div>
        <MasteryBar value={subject.mastery} label={`${subject.name} mastery`} />
      </section>

      <section aria-labelledby="topic-list-title">
        <div className="section-heading-row">
          <h2 id="topic-list-title" className="section-title">Choose a topic</h2>
          <span className="quiet-label">Short sessions, one step at a time</span>
        </div>
        <div className="topic-list">
          {subject.topics.map((topic, index) => (
            <Link className="topic-row" href={`/practice?subject=${subject.id}&topic=${encodeURIComponent(topic.toLowerCase().replaceAll(" ", "-"))}`} key={topic}>
              <span className="topic-number">{String(index + 1).padStart(2, "0")}</span>
              <span className="topic-row-copy"><strong>{topic}</strong><span><Clock3 size={14} aria-hidden="true" /> About 4 minutes</span></span>
              <span className="topic-row-action">Start <ArrowRight size={16} aria-hidden="true" /></span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
