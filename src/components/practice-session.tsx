"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Check, Clock3, Lightbulb, LoaderCircle, X } from "lucide-react";
import { useSession } from "@/components/session-provider";
import { apiWrite } from "@/lib/client-api";
import { getQuestionForTopicAt, getQuestionsForTopic, isSupportedSubject, isSupportedTopic, type PracticeQuestion } from "@/lib/questions";

type SessionResult = { sessionId: string; subjectId: string; topicId: string; questionIndex: number; totalQuestions: number; status: string };
type AnswerResult = { isCorrect: boolean; questionIndex?: number; explanation?: string | null };

function formatTime(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function defaultTopic(subjectId: string) {
  switch (subjectId) {
    case "maths": return "fractions";
    case "english": return "vocabulary";
    case "non-verbal-reasoning": return "rotations";
    default: return "odd-one-out";
  }
}

export function PracticeSession() {
  const searchParams = useSearchParams();
  const { status, csrfToken, refresh: refreshSession } = useSession();
  const requestedSubject = searchParams.get("subject") ?? "verbal-reasoning";
  const requestedTopic = searchParams.get("topic") ?? "odd-one-out";
  const subjectId = isSupportedSubject(requestedSubject) ? requestedSubject : "verbal-reasoning";
  const topicId = isSupportedTopic(subjectId, requestedTopic) ? requestedTopic : defaultTopic(subjectId);
  const sessionKey = `${subjectId}:${topicId}`;
  const questionSet = getQuestionsForTopic(subjectId, topicId);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [hintVisible, setHintVisible] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [answerCorrect, setAnswerCorrect] = useState(false);
  const [answerExplanation, setAnswerExplanation] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [guestElapsed, setGuestElapsed] = useState(42);
  const [complete, setComplete] = useState(false);
  const [sessionState, setSessionState] = useState<"idle" | "starting" | "ready" | "error">("idle");
  const [readySessionKey, setReadySessionKey] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionErrorKey, setSessionErrorKey] = useState<string | null>(null);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const answerRequestRef = useRef<string | null>(null);
  const sessionRequestRef = useRef<{ key: string; promise: Promise<SessionResult> } | null>(null);
  const reduceMotion = useReducedMotion();
  const signedIn = status === "authenticated";
  const requestKey = `${csrfToken ?? "guest"}:${sessionKey}:${retryCount}`;
  const sessionReady = !signedIn || (sessionState === "ready" && readySessionKey === requestKey);
  const sessionStartError = signedIn && sessionState === "error" && sessionErrorKey === requestKey ? sessionError : null;
  const activeQuestionIndex = signedIn && sessionReady ? questionIndex : signedIn ? 0 : questionIndex;
  const current: PracticeQuestion = getQuestionForTopicAt(subjectId, topicId, activeQuestionIndex) ?? questionSet[0];
  const step = signedIn ? activeQuestionIndex + 1 : 5 + activeQuestionIndex;

  useEffect(() => {
    if (status !== "authenticated" || !csrfToken) return;
    let active = true;

    if (!sessionRequestRef.current || sessionRequestRef.current.key !== requestKey) {
      sessionRequestRef.current = {
        key: requestKey,
        promise: apiWrite<SessionResult>("/api/learner/practice/sessions", csrfToken, "POST", {
          subjectId,
          topicId,
          idempotencyKey: crypto.randomUUID(),
        }),
      };
    }

    void sessionRequestRef.current.promise.then(async (result) => {
      if (!active) return;
      setSessionId(result.sessionId);
      setQuestionIndex(result.questionIndex);
      setSessionState("ready");
      setReadySessionKey(requestKey);
      setSessionError(null);
      setSessionErrorKey(null);
      setCompletionError(null);
      setComplete(false);
      setSelected(null);
      setSubmitted(false);
      setAnswerCorrect(false);
      setAnswerExplanation(null);
      setHintVisible(false);
      setAnswerError(null);
      setElapsed(0);
      setGuestElapsed(42);
      answerRequestRef.current = null;
      if (result.questionIndex >= result.totalQuestions || result.status === "completed") {
        try {
          await apiWrite(`/api/learner/practice/sessions/${encodeURIComponent(result.sessionId)}/complete`, csrfToken, "POST", {});
          if (active) { setComplete(true); await refreshSession(); }
        } catch (reason) {
          if (active) setCompletionError(reason instanceof Error ? reason.message : "We couldn’t finish saving your session.");
        }
      }
    }).catch((reason: unknown) => {
      if (active) {
        setSessionState("error");
        setSessionError(reason instanceof Error ? reason.message : "We couldn’t start practice just now.");
        setSessionErrorKey(requestKey);
      }
    });
    return () => { active = false; };
  }, [status, csrfToken, requestKey, sessionKey, retryCount, refreshSession, subjectId, topicId]);

  useEffect(() => {
    if (status !== "guest" && !sessionReady) return;
    if (submitted || complete) return;
    const timer = window.setInterval(() => {
      if (status === "guest") setGuestElapsed((seconds) => seconds + 1);
      else setElapsed((seconds) => seconds + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [status, sessionReady, submitted, complete, activeQuestionIndex]);

  useEffect(() => {
    if (submitted) feedbackRef.current?.focus();
  }, [submitted]);

  async function checkAnswer() {
    if (!selected || submitted || isSubmitting) return;
    setAnswerError(null);
    if (signedIn && (!csrfToken || !sessionId)) {
      setAnswerError("Your practice session isn’t ready yet. Please wait a moment and try again.");
      return;
    }
    setIsSubmitting(true);
    try {
      let result: AnswerResult;
      if (signedIn && csrfToken && sessionId) {
        const idempotencyKey = answerRequestRef.current ?? crypto.randomUUID();
        answerRequestRef.current = idempotencyKey;
        result = await apiWrite<AnswerResult>(`/api/learner/practice/sessions/${encodeURIComponent(sessionId)}/answers`, csrfToken, "POST", {
          questionId: current.id,
          questionIndex,
          selectedAnswer: selected,
          idempotencyKey,
        });
      } else {
        const response = await fetch("/api/practice/check", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ questionId: current.id, selectedAnswer: selected }),
        });
        const body = await response.json() as AnswerResult & { error?: string };
        if (!response.ok) throw new Error(body.error ?? "We couldn’t check your answer just now.");
        result = body;
      }
      setAnswerCorrect(result.isCorrect);
      setAnswerExplanation(result.explanation ?? null);
      setSubmitted(true);
    } catch (reason) {
      setAnswerError(reason instanceof Error ? reason.message : "We couldn’t save your answer just now. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function tryAgain() {
    setSubmitted(false);
    setSelected(null);
    setAnswerCorrect(false);
    setAnswerExplanation(null);
    setAnswerError(null);
    answerRequestRef.current = null;
  }

  async function nextQuestion() {
    if (step >= 8) {
      if (signedIn) {
        if (!csrfToken || !sessionId) { setCompletionError("Your session isn’t ready to finish. Please try again."); return; }
        setCompletionError(null);
        try {
          await apiWrite(`/api/learner/practice/sessions/${encodeURIComponent(sessionId)}/complete`, csrfToken, "POST", {});
          setComplete(true);
          await refreshSession();
        } catch (reason) {
          setCompletionError(reason instanceof Error ? reason.message : "We couldn’t finish saving your session. Please try again.");
        }
      } else {
        setComplete(true);
      }
      return;
    }
    setQuestionIndex((index) => index + 1);
    setSelected(null);
    setHintVisible(false);
    setSubmitted(false);
    setAnswerCorrect(false);
    setAnswerExplanation(null);
    setAnswerError(null);
    answerRequestRef.current = null;
    if (signedIn) setElapsed(0);
    else setGuestElapsed(42);
  }

  if (status === "loading" || (signedIn && !sessionReady && !sessionStartError)) {
    return <main className="practice-frame"><p className="practice-loading" aria-live="polite">Getting your practice ready…</p></main>;
  }

  if (status === "error") {
    return <main className="practice-frame practice-complete"><section className="completion-content"><h1>We couldn’t check your account</h1><p>Refresh Plus11 and try again before saving an answer.</p><Link className="button button-primary" href="/account">Open account <ArrowRight size={17} aria-hidden="true" /></Link><Link className="quiet-link" href="/">Back to Today</Link></section></main>;
  }

  if (signedIn && sessionStartError) {
    return <main className="practice-frame practice-complete"><section className="completion-content"><h1>Practice couldn’t start</h1><p>{sessionStartError}</p><button className="button button-primary" onClick={() => setRetryCount((value) => value + 1)}>Try again <ArrowRight size={17} aria-hidden="true" /></button><Link className="quiet-link" href="/">Back to Today</Link></section></main>;
  }

  if (complete) {
    return (
      <main className="practice-frame practice-complete">
        <Link href="/" className="practice-exit" aria-label="Return to Today"><X size={20} aria-hidden="true" /></Link>
        <div className="completion-content">
          <span className="completion-icon"><Check size={28} strokeWidth={2.5} aria-hidden="true" /></span>
          <h1>Practice complete</h1>
          <p>You’ve finished this set. A little practice goes a long way.</p>
          <Link className="button button-primary" href="/">Back to Today <ArrowRight size={17} aria-hidden="true" /></Link>
          <Link className="quiet-link" href="/learn">Choose another topic</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="practice-frame">
      <header className="practice-header">
        <Link href="/" className="practice-exit" aria-label="Leave practice and return to Today"><X size={20} strokeWidth={2} aria-hidden="true" /></Link>
        <div className="session-progress" aria-label={`Question ${step} of 8`}>
          {Array.from({ length: 8 }, (_, index) => (
            <span key={index} className={`session-segment${index < step - 1 ? " is-done" : index === step - 1 ? " is-current" : ""}`} aria-hidden="true" />
          ))}
          <span className="sr-only">Question {step} of 8</span>
        </div>
        <span className="session-clock"><Clock3 size={17} strokeWidth={2} aria-hidden="true" /> {formatTime(signedIn ? elapsed : guestElapsed)}</span>
      </header>

      <div className="practice-body">
        <div className="practice-context"><span>{current.subject}</span><span>{step} of 8</span></div>

        <motion.section
          className="question-card"
          aria-labelledby="question-title"
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          <Image className="question-owl" src="/plus11-mark.svg" alt="" aria-hidden="true" width={38} height={38} />
          <h1 id="question-title">{current.prompt}</h1>
          <p>{current.support}</p>
        </motion.section>

        <fieldset className="answer-fieldset" disabled={submitted || isSubmitting}>
          <legend className="sr-only">Choose one answer</legend>
          <div className="answer-list">
            {current.options.map(({ letter, text }) => (
              <label className={`answer-option${selected === letter ? " is-selected" : ""}`} key={letter}>
                <input type="radio" name="practice-answer" value={letter} checked={selected === letter} onChange={() => setSelected(letter)} aria-label={`${letter}: ${text}`} />
                <span className="answer-letter" aria-hidden="true">{letter}</span>
                <span className="answer-text">{text}</span>
                {selected === letter ? <Check className="answer-selected-check" size={17} strokeWidth={2.5} aria-hidden="true" /> : null}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="practice-bottom">
          <AnimatePresence initial={false}>
            {hintVisible ? (
              <motion.p key="hint" className="hint-message" initial={reduceMotion ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={reduceMotion ? undefined : { opacity: 0, y: -2 }} transition={{ duration: reduceMotion ? 0 : 0.18 }}>
                <Lightbulb size={18} aria-hidden="true" /><span><strong>A little hint</strong>{current.hint}</span>
              </motion.p>
            ) : null}
          </AnimatePresence>

          {answerError ? <p className="account-message account-message-error" role="alert">{answerError}</p> : null}
          {completionError ? <p className="account-message account-message-error" role="alert">{completionError}</p> : null}

          {submitted ? (
            <div className={`answer-feedback${answerCorrect ? " feedback-correct" : " feedback-try-again"}`} ref={feedbackRef} tabIndex={-1} role="status" aria-live="polite">
              <span className="feedback-icon" aria-hidden="true">{answerCorrect ? <Check size={18} strokeWidth={2.5} /> : <Lightbulb size={18} />}</span>
              <div className="feedback-copy">
                <strong>{answerCorrect ? "That’s right." : "Not quite yet."}</strong>
                <p>{answerCorrect ? answerExplanation ?? "That is the right answer." : "Have another look at the hint above, then try a different answer."}</p>
              </div>
              {answerCorrect ? (
                <button className="button button-primary feedback-action" onClick={() => void nextQuestion()}>{step >= 8 ? "Finish" : "Continue"} <ArrowRight size={16} aria-hidden="true" /></button>
              ) : (
                <button className="button button-secondary feedback-action" onClick={tryAgain}>Try again</button>
              )}
            </div>
          ) : (
            <div className="practice-actions">
              <button className={`button button-secondary hint-button${hintVisible ? " is-open" : ""}`} onClick={() => setHintVisible((visible) => !visible)} aria-expanded={hintVisible}>
                <Lightbulb size={17} strokeWidth={2} aria-hidden="true" /> {hintVisible ? "Hide hint" : "Hint"}
              </button>
              <button className="button button-primary check-button" onClick={() => void checkAnswer()} disabled={!selected || isSubmitting}>
                {isSubmitting ? <><LoaderCircle className="account-spinner" size={16} aria-hidden="true" /> Checking…</> : <>Check answer <ArrowRight size={17} aria-hidden="true" /></>}
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
