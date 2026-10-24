"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpenCheck, Check, LoaderCircle, RotateCcw } from "lucide-react";
import { useSession } from "@/components/session-provider";
import { apiGet, apiWrite } from "@/lib/client-api";
import { reviewCards } from "@/lib/data";

type Card = { cardId: string; topic: string; prompt: string; answer: string };
type DueReviewResponse = { cards: Card[]; dueCount: number };
const demoCards = reviewCards.map((card, index) => ({ ...card, cardId: `sample-${index + 1}` }));

export function ReviewScreen() {
  const { status, csrfToken, error: sessionError, refresh: refreshSession } = useSession();
  const [reviewRecord, setReviewRecord] = useState<{ key: string; cards: Card[] } | null>(null);
  const [loadError, setLoadError] = useState<{ key: string; message: string } | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [started, setStarted] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);
  const [current, setCurrent] = useState(0);
  const [revisitCount, setRevisitCount] = useState(0);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const eventRef = useRef<{ cardId: string; eventId: string } | null>(null);
  const requestKey = status === "authenticated" && csrfToken ? `${csrfToken}:${reloadKey}` : null;

  useEffect(() => {
    if (status !== "authenticated" || !csrfToken) return;
    let active = true;
    void apiGet<DueReviewResponse>("/api/learner/review").then((result) => {
      if (active) setReviewRecord({ key: `${csrfToken}:${reloadKey}`, cards: result.cards });
    }).catch((reason: unknown) => { if (active) setLoadError({ key: `${csrfToken}:${reloadKey}`, message: reason instanceof Error ? reason.message : "We couldn’t load your review cards just now." }); });
    return () => { active = false; };
  }, [status, csrfToken, reloadKey]);

  const cards = requestKey && reviewRecord?.key === requestKey ? reviewRecord.cards : null;
  const reviewError = requestKey && loadError?.key === requestKey ? loadError.message : null;

  if (status === "loading" || (status === "authenticated" && cards === null && !reviewError)) {
    return <div className="page-stack review-page" aria-live="polite"><section className="page-intro"><h1 className="page-title">A quick look back</h1><p>Getting your review cards ready…</p></section><div className="review-loading-state"><span className="review-spinner" aria-hidden="true" /> Loading your review cards</div></div>;
  }
  if (status === "error" || reviewError) {
    return <div className="page-stack review-page"><section className="page-intro"><h1 className="page-title">A quick look back</h1><p>We couldn’t load your review cards just now.</p></section><section className="account-state-card" role="alert"><p>{status === "error" ? sessionError : reviewError}</p><button className="button button-secondary" onClick={() => status === "error" ? void refreshSession() : setReloadKey((key) => key + 1)}>Try again</button></section></div>;
  }

  const signedIn = status === "authenticated";
  const list = signedIn ? cards ?? [] : demoCards;
  const dueCount = list.length;
  const estimate = dueCount ? Math.max(1, Math.round(dueCount * 40 / 60)) : 0;
  const finished = current >= dueCount;
  const card = list[current];

  async function recordOutcome(outcome: "got-it" | "again") {
    if (!card) return;
    setActionError(null);
    if (signedIn) {
      if (!csrfToken) { setActionError("Refresh your account before saving this review."); return; }
      if (!eventRef.current || eventRef.current.cardId !== card.cardId) eventRef.current = { cardId: card.cardId, eventId: crypto.randomUUID() };
      setSaving(true);
      try {
        await apiWrite(`/api/learner/review/${encodeURIComponent(card.cardId)}`, csrfToken, "POST", { outcome, eventId: eventRef.current.eventId });
      } catch (reason) {
        setActionError(reason instanceof Error ? reason.message : "We couldn’t save this review just now. Please try again.");
        setSaving(false);
        return;
      }
      eventRef.current = null;
      setSaving(false);
    }
    if (outcome === "again") setRevisitCount((count) => count + 1);
    setShowAnswer(false);
    setCurrent((value) => value + 1);
  }

  return (
    <div className="page-stack review-page">
      <section className="page-intro" aria-labelledby="review-title">
        <h1 id="review-title" className="page-title">A quick look back</h1>
        <p>Little reviews help ideas stick.</p>
        {!signedIn ? <span className="demo-label">Example review cards</span> : null}
      </section>

      {dueCount === 0 ? (
        <section className="review-finished" aria-live="polite">
          <span className="finished-mark"><Check size={28} strokeWidth={2.5} aria-hidden="true" /></span>
          <h2>You’re all caught up.</h2>
          <p>{signedIn ? "There are no cards due just now. Missed questions will appear here when they’re ready to review." : "There are no cards to review right now. Come back after your next practice."}</p>
          <Link className="button button-primary" href="/">Back to Today <ArrowRight size={17} aria-hidden="true" /></Link>
        </section>
      ) : !started ? (
        <>
          <section className="review-summary" aria-label={`Review ${dueCount} cards due today`}>
            <div className="review-summary-icon"><BookOpenCheck size={23} strokeWidth={2} aria-hidden="true" /></div>
            <div className="review-summary-copy"><h2>{dueCount} {dueCount === 1 ? "card is" : "cards are"} ready to review</h2><p>About {estimate} minute{estimate === 1 ? "" : "s"}, at your own pace.</p></div>
            <span className="review-count" aria-label={`${dueCount} cards`}>{dueCount}</span>
          </section>
          <div className="review-queue" aria-label="Topics in your review queue">
            {list.slice(0, 4).map((item, index) => (
              <div className="review-queue-row" key={item.cardId}>
                <span className="queue-index">{String(index + 1).padStart(2, "0")}</span>
                <span>{item.topic}</span>
                <span className="queue-dot" aria-hidden="true" />
              </div>
            ))}
            {dueCount > 4 ? <p className="queue-more">Plus {dueCount - 4} more {dueCount - 4 === 1 ? "card" : "cards"}</p> : null}
          </div>
          <button className="button button-primary review-start" onClick={() => { setCurrent(0); setStarted(true); }}>
            Start review <ArrowRight size={17} aria-hidden="true" />
          </button>
          <Link className="quiet-link" href="/learn">Choose a topic instead</Link>
        </>
      ) : finished ? (
        <section className="review-finished" aria-live="polite">
          <span className="finished-mark"><Check size={28} strokeWidth={2.5} aria-hidden="true" /></span>
          <h2>That’s your review done.</h2>
          <p>{revisitCount > 0 ? `You’ve revisited all ${dueCount} cards. ${revisitCount} ${revisitCount === 1 ? "card is" : "cards are"} ready for another look.` : `You’ve revisited all ${dueCount} cards. Nice steady work.`}</p>
          <Link className="button button-primary" href="/">Back to Today <ArrowRight size={17} aria-hidden="true" /></Link>
        </section>
      ) : card ? (
        <section className="review-session" aria-labelledby="review-card-title">
          <div className="review-session-meta"><span>Card {current + 1} of {dueCount}</span><span className="review-topic-tag">{card.topic}</span></div>
          <div className="review-session-progress" role="progressbar" aria-label="Review progress" aria-valuemin={0} aria-valuemax={dueCount} aria-valuenow={current}>
            <span style={{ width: `${current / dueCount * 100}%` }} />
          </div>
          <div className="review-flashcard">
            <span className="card-side-label">Have a think</span>
            <h2 id="review-card-title">{card.prompt}</h2>
            {showAnswer ? <div className="review-answer" aria-live="polite"><span className="card-side-label">A helpful answer</span><p>{card.answer}</p></div> : null}
          </div>
          {actionError ? <p className="account-message account-message-error" role="alert">{actionError}</p> : null}
          {!showAnswer ? (
            <button className="button button-primary review-reveal" onClick={() => setShowAnswer(true)}>Show answer <ArrowRight size={17} aria-hidden="true" /></button>
          ) : (
            <div className="review-actions">
              <button className="button button-secondary" disabled={saving} onClick={() => void recordOutcome("again")}><RotateCcw size={16} aria-hidden="true" /> {saving ? "Saving…" : "Need another look"}</button>
              <button className="button button-primary" disabled={saving} onClick={() => void recordOutcome("got-it")}><Check size={16} aria-hidden="true" /> {saving ? "Saving…" : "Got it"}</button>
            </div>
          )}
          {saving ? <span className="sr-only" role="status"><LoaderCircle size={16} aria-hidden="true" /> Saving your review</span> : null}
        </section>
      ) : null}
    </div>
  );
}
