"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpenCheck, Check, RotateCcw } from "lucide-react";
import { reviewCards } from "@/lib/data";

export function ReviewScreen() {
  const [started, setStarted] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);
  const [current, setCurrent] = useState(0);
  const [revisitCount, setRevisitCount] = useState(0);
  const finished = current >= reviewCards.length;
  const card = reviewCards[current];

  return (
    <div className="page-stack review-page">
      <section className="page-intro" aria-labelledby="review-title">
        <h1 id="review-title" className="page-title">A quick look back</h1>
        <p>Little reviews help ideas stick.</p>
      </section>

      {reviewCards.length === 0 ? (
        <section className="review-finished" aria-live="polite">
          <span className="finished-mark"><Check size={28} strokeWidth={2.5} aria-hidden="true" /></span>
          <h2>You’re all caught up.</h2>
          <p>There are no cards to review right now. Come back after your next practice.</p>
          <Link className="button button-primary" href="/">Back to Today <ArrowRight size={17} aria-hidden="true" /></Link>
        </section>
      ) : !started ? (
        <>
          <section className="review-summary" aria-label="Review due today">
            <div className="review-summary-icon"><BookOpenCheck size={23} strokeWidth={2} aria-hidden="true" /></div>
            <div className="review-summary-copy"><h2>6 cards are ready to review</h2><p>About 4 minutes, at your own pace.</p></div>
            <span className="review-count">6</span>
          </section>
          <div className="review-queue" aria-label="Topics in your review queue">
            {reviewCards.slice(0, 4).map((item, index) => (
              <div className="review-queue-row" key={item.topic}>
                <span className="queue-index">0{index + 1}</span>
                <span>{item.topic}</span>
                <span className="queue-dot" aria-hidden="true" />
              </div>
            ))}
            <p className="queue-more">Plus 2 more cards</p>
          </div>
          <button className="button button-primary review-start" onClick={() => setStarted(true)}>
            Start review <ArrowRight size={17} aria-hidden="true" />
          </button>
          <Link className="quiet-link" href="/learn">Choose a topic instead</Link>
        </>
      ) : finished ? (
        <section className="review-finished" aria-live="polite">
          <span className="finished-mark"><Check size={28} strokeWidth={2.5} aria-hidden="true" /></span>
          <h2>That’s your review done.</h2>
          <p>{revisitCount > 0 ? `You’ve revisited all 6 cards. ${revisitCount} ${revisitCount === 1 ? "card is" : "cards are"} ready for another look.` : "You’ve revisited all 6 cards. Nice steady work."}</p>
          <Link className="button button-primary" href="/">Back to Today <ArrowRight size={17} aria-hidden="true" /></Link>
        </section>
      ) : card ? (
        <section className="review-session" aria-labelledby="review-card-title">
          <div className="review-session-meta"><span>Card {current + 1} of 6</span><span className="review-topic-tag">{card.topic}</span></div>
          <div className="review-session-progress" role="progressbar" aria-label="Review progress" aria-valuemin={0} aria-valuemax={6} aria-valuenow={current}>
            <span style={{ width: `${current / 6 * 100}%` }} />
          </div>
          <div className="review-flashcard">
            <span className="card-side-label">Have a think</span>
            <h2 id="review-card-title">{card.prompt}</h2>
            {showAnswer ? <div className="review-answer" aria-live="polite"><span className="card-side-label">A helpful answer</span><p>{card.answer}</p></div> : null}
          </div>
          {!showAnswer ? (
            <button className="button button-primary review-reveal" onClick={() => setShowAnswer(true)}>Show answer <ArrowRight size={17} aria-hidden="true" /></button>
          ) : (
            <div className="review-actions">
              <button className="button button-secondary" onClick={() => { setRevisitCount((count) => count + 1); setShowAnswer(false); setCurrent((value) => value + 1); }}><RotateCcw size={16} aria-hidden="true" /> Need another look</button>
              <button className="button button-primary" onClick={() => { setShowAnswer(false); setCurrent((value) => value + 1); }}><Check size={16} aria-hidden="true" /> Got it</button>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
