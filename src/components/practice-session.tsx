"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Check, Clock3, Lightbulb, LoaderCircle, X } from "lucide-react";
import { useSession } from "@/components/session-provider";
import { apiGet, apiWrite } from "@/lib/client-api";
import { getQuestionForTopicAt, getQuestionsForTopic, isSupportedSubject, isSupportedTopic } from "@/lib/questions";

type SessionResult = {
  sessionId: string;
  subjectId: string;
  topicId: string;
  questionIndex: number;
  totalQuestions: number;
  status: string;
  state?: string;
  question: DisplayQuestion | null;
};
type DisplayQuestion = {
  id: string;
  subject: string;
  prompt: string;
  support: string;
  hint: string;
  options: { letter: string; text: string }[];
};
type AnswerResult = {
  isCorrect: boolean;
  questionIndex?: number;
  correctAnswer?: string | null;
  explanation?: string | null;
  session?: SessionResult;
};

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

const guestFallback = getQuestionForTopicAt("verbal-reasoning", "odd-one-out", 0)!;

export function PracticeSession() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { status, csrfToken, refresh: refreshSession } = useSession();
  const demoMode = searchParams.get("demo") === "1";
  const requestedSubject = searchParams.get("subject") ?? "verbal-reasoning";
  const requestedTopic = searchParams.get("topic") ?? "odd-one-out";
  const signedIn = status === "authenticated" && !demoMode;
  const subjectId = signedIn
    ? requestedSubject.slice(0, 100)
    : isSupportedSubject(requestedSubject) ? requestedSubject : "verbal-reasoning";
  const topicId = signedIn
    ? requestedTopic.slice(0, 140)
    : isSupportedTopic(subjectId, requestedTopic) ? requestedTopic : defaultTopic(subjectId);
  const sessionKey = `${subjectId}:${topicId}`;
  const requestedSessionId = signedIn ? searchParams.get("sessionId") : null;
  const questionSet = getQuestionsForTopic(subjectId, topicId);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [serverQuestion, setServerQuestion] = useState<DisplayQuestion | null>(null);
  const [totalQuestions, setTotalQuestions] = useState(8);
  const [selected, setSelected] = useState<string | null>(null);
  const [hintVisible, setHintVisible] = useState(false);
  const [hintUsed, setHintUsed] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [answerCorrect, setAnswerCorrect] = useState(false);
  const [answerCorrectText, setAnswerCorrectText] = useState<string | null>(null);
  const [answerExplanation, setAnswerExplanation] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [retrying, setRetryingFlag] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [guestElapsed, setGuestElapsed] = useState(42);
  const [complete, setComplete] = useState(false);
  const [sessionState, setSessionState] = useState<"idle" | "starting" | "ready" | "error">("idle");
  const [readySessionKey, setReadySessionKey] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(requestedSessionId);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionErrorKey, setSessionErrorKey] = useState<string | null>(null);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const answerRequestRef = useRef<{ key: string; questionId: string; selected: string } | null>(null);
  const sessionRequestRef = useRef<{ key: string; promise: Promise<SessionResult> } | null>(null);
  const pendingSessionRef = useRef<SessionResult | null>(null);
  const reduceMotion = useReducedMotion();
  const requestKey = `${csrfToken ?? "guest"}:${sessionKey}:${retryCount}:${requestedSessionId ?? "new"}`;
  const sessionReady = !signedIn || (sessionState === "ready" && readySessionKey === requestKey);
  const sessionStartError = !signedIn ? null
    : !csrfToken ? "Refresh your account before saving your learning."
    : sessionState === "error" && sessionErrorKey === requestKey ? sessionError : null;
  const activeQuestionIndex = signedIn && sessionReady ? questionIndex : signedIn ? 0 : questionIndex;
  const demoQuestion = getQuestionForTopicAt(subjectId, topicId, activeQuestionIndex) ?? questionSet[0] ?? guestFallback;
  const current: DisplayQuestion = signedIn ? serverQuestion ?? demoQuestion : demoQuestion;
  const totalSteps = signedIn ? totalQuestions : 8;
  const step = signedIn ? activeQuestionIndex + 1 : 5 + activeQuestionIndex;

  useEffect(() => {
    if (status !== "authenticated" || demoMode || !csrfToken) return;
    let active = true;

    if (!sessionRequestRef.current || sessionRequestRef.current.key !== requestKey) {
      const promise = requestedSessionId
        ? apiGet<SessionResult>(`/api/learner/practice/sessions/${encodeURIComponent(requestedSessionId)}`)
        : apiWrite<SessionResult>("/api/learner/practice/sessions", csrfToken, "POST", {
            subjectId,
            topicId,
            idempotencyKey: crypto.randomUUID(),
          });
      sessionRequestRef.current = { key: requestKey, promise };
    }

    void sessionRequestRef.current.promise.then(async (result) => {
      if (!active) return;
      if (!requestedSessionId) {
        const nextKey = `${csrfToken}:${sessionKey}:${retryCount}:${result.sessionId}`;
        sessionRequestRef.current = { key: nextKey, promise: Promise.resolve(result) };
        const query = new URLSearchParams(searchParams.toString());
        query.set("sessionId", result.sessionId);
        router.replace(`/practice?${query.toString()}`, { scroll: false });
      }
      setSessionId(result.sessionId);
      setQuestionIndex(result.questionIndex);
      setTotalQuestions(result.totalQuestions);
      setServerQuestion(result.question);
      setSessionState("ready");
      setReadySessionKey(requestKey);
      setSessionError(null);
      setSessionErrorKey(null);
      setCompletionError(null);
      setComplete(false);
      setSelected(null);
      setSubmitted(false);
      setAnswerCorrect(false);
      setAnswerCorrectText(null);
      setAnswerExplanation(null);
      setHintVisible(false);
      setHintUsed(false);
      setAnswerError(null);
      setElapsed(0);
      answerRequestRef.current = null;
      pendingSessionRef.current = null;

      if (result.status === "complete" || result.state === "complete") {
        setComplete(true);
        await refreshSession();
      } else if (result.questionIndex >= result.totalQuestions) {
        try {
          await apiWrite(`/api/learner/practice/sessions/${encodeURIComponent(result.sessionId)}/complete`, csrfToken, "POST", {});
          if (active) { setComplete(true); await refreshSession(); }
        } catch (reason) {
          if (active) setCompletionError(reason instanceof Error ? reason.message : "We couldn’t finish saving your session.");
        }
      } else if (!result.question) {
        setSessionState("error");
        setSessionError("There isn’t a reviewed question ready for this topic yet. Choose another topic from Learn.");
        setSessionErrorKey(requestKey);
      }
    }).catch((reason: unknown) => {
      if (active) {
        setSessionState("error");
        setSessionError(reason instanceof Error ? reason.message : "We couldn’t start practice just now.");
        setSessionErrorKey(requestKey);
      }
    });
    return () => { active = false; };
  }, [status, csrfToken, requestKey, sessionKey, retryCount, refreshSession, subjectId, topicId, requestedSessionId, demoMode, router, searchParams]);

  useEffect(() => {
    if (status === "loading" || (signedIn && !sessionReady)) return;
    if (submitted || complete) return;
    const timer = window.setInterval(() => {
      if (!signedIn) setGuestElapsed((seconds) => seconds + 1);
      else setElapsed((seconds) => seconds + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [status, signedIn, sessionReady, submitted, complete, activeQuestionIndex]);

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
        const previousRequest = answerRequestRef.current;
        const idempotencyKey = previousRequest?.questionId === current.id && previousRequest.selected === selected
          ? previousRequest.key
          : crypto.randomUUID();
        answerRequestRef.current = { key: idempotencyKey, questionId: current.id, selected };
        result = await apiWrite<AnswerResult>(`/api/learner/practice/sessions/${encodeURIComponent(sessionId)}/answers`, csrfToken, "POST", {
          questionId: current.id,
          questionIndex,
          selectedAnswer: selected,
          idempotencyKey,
          timeTakenMs: elapsed * 1000,
          hintUsed,
          action: retrying ? "retry" : "answer",
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
      pendingSessionRef.current = result.session ?? null;
      setAnswerCorrect(result.isCorrect);
      setAnswerCorrectText(result.correctAnswer ?? null);
      setAnswerExplanation(result.explanation ?? null);
      setSubmitted(true);
    } catch (reason) {
      setAnswerError(reason instanceof Error ? reason.message : "We couldn’t save your answer just now. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function tryAgain() {
    setAnswerError(null);
    if (signedIn) {
      if (!csrfToken || !sessionId) { setAnswerError("Refresh your account before retrying this question."); return; }
      setIsRetrying(true);
      try {
        const result = await apiWrite<{ hint: string; session: SessionResult }>(
          `/api/learner/practice/sessions/${encodeURIComponent(sessionId)}/retry`, csrfToken, "POST", {},
        );
        setQuestionIndex(result.session.questionIndex);
        setServerQuestion(result.session.question);
        setTotalQuestions(result.session.totalQuestions);
      } catch (reason) {
        setAnswerError(reason instanceof Error ? reason.message : "We couldn’t reopen this question just now.");
        setIsRetrying(false);
        return;
      }
      setIsRetrying(false);
    }
    pendingSessionRef.current = null;
    answerRequestRef.current = null;
    setRetryingFlag(signedIn);
    setSubmitted(false);
    setSelected(null);
    setAnswerCorrect(false);
    setAnswerCorrectText(null);
    setAnswerExplanation(null);
    setHintVisible(false);
    setHintUsed(false);
    if (signedIn) setElapsed(0);
  }

  async function nextQuestion() {
    if (step >= totalSteps) {
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
    if (signedIn && sessionId) {
      try {
        const next = pendingSessionRef.current ?? await apiGet<SessionResult>(`/api/learner/practice/sessions/${encodeURIComponent(sessionId)}`);
        if (!next.question || next.questionIndex >= next.totalQuestions) {
          setCompletionError("This practice set has no more reviewed questions. Finish to save your progress.");
          return;
        }
        setQuestionIndex(next.questionIndex);
        setTotalQuestions(next.totalQuestions);
        setServerQuestion(next.question);
        pendingSessionRef.current = null;
      } catch (reason) {
        setCompletionError(reason instanceof Error ? reason.message : "We couldn’t load the next question just now.");
        return;
      }
    } else {
      setQuestionIndex((index) => index + 1);
    }
    setSelected(null);
    setHintVisible(false);
    setHintUsed(false);
    setSubmitted(false);
    setAnswerCorrect(false);
    setAnswerCorrectText(null);
    setAnswerExplanation(null);
    setAnswerError(null);
    answerRequestRef.current = null;
    setRetryingFlag(false);
    if (signedIn) setElapsed(0);
    else setGuestElapsed(42);
  }

  if (status === "loading") {
    return <main className="practice-frame"><p className="practice-loading" aria-live="polite">Getting your practice ready…</p></main>;
  }

  if (status === "error" && !demoMode) {
    return <main className="practice-frame practice-complete"><section className="completion-content"><h1>We couldn’t check your account</h1><p>Refresh Plus11 and try again before saving an answer.</p><Link className="button button-primary" href="/account">Open account <ArrowRight size={17} aria-hidden="true" /></Link><Link className="quiet-link" href="/">Back to Today</Link></section></main>;
  }

  if (signedIn && !sessionReady && !sessionStartError) {
    return <main className="practice-frame"><p className="practice-loading" aria-live="polite">Getting your practice ready…</p></main>;
  }

  if (signedIn && sessionStartError) {
    return <main className="practice-frame practice-complete"><section className="completion-content"><h1>Practice couldn’t start</h1><p>{sessionStartError}</p><button className="button button-primary" onClick={() => setRetryCount((value) => value + 1)}>Try again <ArrowRight size={17} aria-hidden="true" /></button><Link className="quiet-link" href="/learn">Choose another topic</Link></section></main>;
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
        <div className="session-progress" aria-label={`Question ${step} of ${totalSteps}`}>
          {Array.from({ length: totalSteps }, (_, index) => (
            <span key={index} className={`session-segment${index < step - 1 ? " is-done" : index === step - 1 ? " is-current" : ""}`} aria-hidden="true" />
          ))}
          <span className="sr-only">Question {step} of {totalSteps}</span>
        </div>
        <span className="session-clock"><Clock3 size={17} strokeWidth={2} aria-hidden="true" /> {formatTime(signedIn ? elapsed : guestElapsed)}</span>
      </header>

      <div className="practice-body">
        <div className="practice-context"><span>{current.subject}</span><span>{step} of {totalSteps}</span></div>

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

        <fieldset className="answer-fieldset" disabled={submitted || isSubmitting || isRetrying}>
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
                <p>{answerCorrect ? answerExplanation ?? "That is the right answer." : answerExplanation ?? (answerCorrectText ? `The answer is ${answerCorrectText}. Have another look at the hint above, then try again.` : "Have another look at the hint above, then try a different answer.")}</p>
              </div>
              {answerCorrect ? (
                <button className="button button-primary feedback-action" onClick={() => void nextQuestion()}>{step >= totalSteps ? "Finish" : "Continue"} <ArrowRight size={16} aria-hidden="true" /></button>
              ) : (
                <button className="button button-secondary feedback-action" disabled={isRetrying} onClick={() => void tryAgain()}>{isRetrying ? "Opening…" : "Try again"}</button>
              )}
            </div>
          ) : (
            <div className="practice-actions">
              <button className={`button button-secondary hint-button${hintVisible ? " is-open" : ""}`} onClick={() => { if (!hintVisible) setHintUsed(true); setHintVisible((visible) => !visible); }} aria-expanded={hintVisible}>
                <Lightbulb size={17} strokeWidth={2} aria-hidden="true" /> {hintVisible ? "Hide hint" : "Hint"}
              </button>
              <button className="button button-primary check-button" onClick={() => void checkAnswer()} disabled={!selected || isSubmitting || isRetrying}>
                {isSubmitting ? <><LoaderCircle className="account-spinner" size={16} aria-hidden="true" /> Checking…</> : <>Check answer <ArrowRight size={17} aria-hidden="true" /></>}
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
