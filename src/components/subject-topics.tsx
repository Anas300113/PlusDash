"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ArrowRight, BookOpen, Clock3, LoaderCircle, Shapes } from "lucide-react";
import { MasteryBar } from "@/components/progress-indicators";
import { useSession } from "@/components/session-provider";
import { apiGet } from "@/lib/client-api";
import { subjects } from "@/lib/data";

type CatalogTopic = { id: string; name: string; approvedQuestionCount: number; attempts: number; mastery: number };
type CatalogSubject = { id: string; subjectId: string; name: string; mastery: number; attempts: number; topicCount: number; topics: CatalogTopic[] };
type CatalogResponse = { subjects: CatalogSubject[] };

export function SubjectTopics() {
  const params = useParams<{ subject: string }>();
  const { status, csrfToken, error: sessionError, refresh: refreshSession } = useSession();
  const [catalogRecord, setCatalogRecord] = useState<{ key: string; data: CatalogResponse } | null>(null);
  const [loadError, setLoadError] = useState<{ key: string; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const requestKey = status === "authenticated" && csrfToken ? `${csrfToken}:${reloadKey}` : null;

  useEffect(() => {
    if (status !== "authenticated" || !csrfToken) return;
    let active = true;
    void apiGet<CatalogResponse>("/api/learner/catalog").then((data) => {
      if (active) setCatalogRecord({ key: `${csrfToken}:${reloadKey}`, data });
    }).catch((reason: unknown) => {
      if (active) setLoadError({ key: `${csrfToken}:${reloadKey}`, message: reason instanceof Error ? reason.message : "We couldn’t load this subject just now." });
    });
    return () => { active = false; };
  }, [status, csrfToken, reloadKey]);

  const catalog = requestKey && catalogRecord?.key === requestKey ? catalogRecord.data : null;
  const catalogError = requestKey && loadError?.key === requestKey ? loadError.message : null;
  const signedIn = status === "authenticated";
  const accountSubject = catalog?.subjects.find((item) => item.id === params.subject || item.subjectId === params.subject);
  const demoSubject = subjects.find((item) => item.id === params.subject);

  if (status === "loading" || (signedIn && catalog === null && !catalogError)) {
    return <div className="page-stack topic-page" aria-live="polite"><section className="page-intro"><h1 className="page-title">Getting your subjects ready…</h1></section><div className="account-state-card"><LoaderCircle className="account-spinner" size={22} aria-hidden="true" /> Loading reviewed topics</div></div>;
  }
  if (status === "error" || catalogError) {
    return <div className="page-stack topic-page"><section className="page-intro"><h1 className="page-title">We couldn’t load this subject</h1></section><section className="account-state-card" role="alert"><p>{status === "error" ? sessionError : catalogError}</p><button className="button button-secondary" onClick={() => status === "error" ? void refreshSession() : setReloadKey((key) => key + 1)}>Try again</button><Link className="quiet-link" href="/learn">All subjects</Link></section></div>;
  }

  const selected = signedIn ? accountSubject : demoSubject;
  if (!selected) {
    return <section className="page-stack not-found-card"><h1 className="page-title">Let’s find that subject</h1><p>That subject isn’t here yet. Choose from the subjects you can practise.</p><Link className="button button-primary" href="/learn"><ArrowLeft size={17} /> Back to Learn</Link></section>;
  }

  const Icon = subjects.find((item) => item.id === selected.id || ("subjectId" in selected && item.id === selected.subjectId))?.icon ?? BookOpen;
  const topicRows = signedIn
    ? (accountSubject?.topics ?? []).map((topic) => ({ id: topic.id, name: topic.name, approvedCount: topic.approvedQuestionCount, attempts: topic.attempts }))
    : (demoSubject?.topics ?? []).map((name) => ({ id: name.toLowerCase().replaceAll(" ", "-"), name, approvedCount: 1, attempts: 0 }));
  const practiceSubjectId = signedIn ? accountSubject?.subjectId ?? selected.id : selected.id;

  return (
    <div className="page-stack topic-page">
      <Link className="back-link" href="/learn"><ArrowLeft size={17} aria-hidden="true" /> All subjects</Link>
      <section className="topic-intro">
        <span className="subject-icon subject-icon-large"><Icon size={24} strokeWidth={2} aria-hidden="true" /></span>
        <div><h1 className="page-title">{selected.name}</h1><p>Pick a topic for a short practice.</p>{!signedIn ? <span className="demo-label">Example topics</span> : null}</div>
      </section>

      <section className="topic-overview" aria-label={`${selected.name} mastery`}>
        <div className="topic-overview-copy"><strong>{selected.mastery}% mastered</strong><span>{selected.topicCount} topics</span></div>
        <MasteryBar value={selected.mastery} label={`${selected.name} mastery`} />
      </section>

      <section aria-labelledby="topic-list-title">
        <div className="section-heading-row"><h2 id="topic-list-title" className="section-title">Choose a topic</h2><span className="quiet-label">Short sessions, one step at a time</span></div>
        {topicRows.length ? (
          <div className="topic-list">
            {topicRows.map((topic, index) => topic.approvedCount > 0 ? (
              <Link className="topic-row" href={`/practice?subject=${encodeURIComponent(practiceSubjectId)}&topic=${encodeURIComponent(topic.id)}`} key={topic.id}>
                <span className="topic-number">{String(index + 1).padStart(2, "0")}</span>
                <span className="topic-row-copy"><strong>{topic.name}</strong><span><Clock3 size={14} aria-hidden="true" /> {signedIn ? `${topic.approvedCount} reviewed question${topic.approvedCount === 1 ? "" : "s"}${topic.attempts ? ` · ${topic.attempts} answers saved` : ""}` : "About 4 minutes"}</span></span>
                <span className="topic-row-action">Start <ArrowRight size={16} aria-hidden="true" /></span>
              </Link>
            ) : (
              <div className="topic-row topic-row-disabled" key={topic.id} aria-disabled="true"><span className="topic-number">{String(index + 1).padStart(2, "0")}</span><span className="topic-row-copy"><strong>{topic.name}</strong><span>Reviewed questions are being prepared</span></span><Shapes size={18} aria-hidden="true" /></div>
            ))}
          </div>
        ) : (
          <div className="account-state-card"><p>There aren’t any reviewed questions for this subject yet. You can try a sample question instead.</p><Link className="button button-primary" href="/practice?subject=verbal-reasoning&topic=odd-one-out&demo=1">Try a sample <ArrowRight size={17} aria-hidden="true" /></Link></div>
        )}
      </section>
    </div>
  );
}
