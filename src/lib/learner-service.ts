import "server-only";

import { AppError } from "@/lib/errors";

export type LearnerProfile = { displayName: string; streakDays: number };
export type ReviewCard = {
  cardId: string;
  subjectId: string;
  topicId: string;
  topic: string;
  prompt: string;
  answer?: string;
  explanation?: string;
};
export type PracticeQuestion = {
  id: string;
  subjectId: string;
  topicId: string;
  subject: string;
  topic: string;
  prompt: string;
  support: string;
  hint: string;
  options: { letter: string; text: string }[];
};
export type PracticeSession = {
  sessionId: string;
  subjectId: string;
  topicId: string;
  questionIndex: number;
  totalQuestions: number;
  status: string;
  question: PracticeQuestion | null;
  state: string;
};
export type LearnerSubject = {
  id: string;
  subjectId: string;
  name: string;
  mastery: number;
  attempts: number;
  topicCount: number;
  topics: {
    id: string;
    name: string;
    approvedQuestionCount: number;
    attempts: number;
    mastery: number;
  }[];
};
export type ProgressData = {
  overall: number;
  totalAttempts: number;
  hasHistory: boolean;
  mastery: { id: string; name: string; mastery: number; attempts: number }[];
  minutesByDay: { date: string; label: string; state: "complete" | "today" | "upcoming" | "missed"; minutes: number }[];
  practiceDays: number;
  nextStep: { subjectId: string; topicId: string; title: string; detail: string; href: string };
};

function apiBase(): URL {
  const raw = process.env.PLUS_API_BASE_URL ?? "http://127.0.0.1:8001";
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new AppError("The learning service is not configured.", 503, "learning_service_unavailable");
  }
  if (parsed.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(parsed.hostname)) {
    throw new AppError("The learning service must use the private loopback listener.", 503, "learning_service_unavailable");
  }
  return new URL("/", parsed.origin);
}

async function backend<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  if (!token) throw new AppError("Please sign in to save your learning.", 401, "unauthenticated");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  let response: Response;
  try {
    response = await fetch(new URL(path.replace(/^\/+/, ""), apiBase()), {
      ...init,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new AppError("We couldn’t reach your learning just now. Please try again.", 503, "learning_service_unavailable");
  }
  const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : "";
    const message = response.status >= 500
      ? "We couldn’t reach your learning just now. Please try again."
      : detail || "We couldn’t complete that just now. Please try again.";
    throw new AppError(message, response.status, response.status === 409 ? "learning_conflict" : "learning_backend_error");
  }
  if (payload === null) throw new AppError("The learning service returned an invalid response.", 502, "learning_service_invalid_response");
  return payload as T;
}

function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

export async function getLearnerProfile(token: string): Promise<LearnerProfile> {
  const result = await backend<{ display_name: string; streak_days: number }>(token, "/api/me/profile");
  return { displayName: result.display_name, streakDays: result.streak_days };
}

export async function updateLearnerName(token: string, displayName: string): Promise<LearnerProfile> {
  const result = await backend<{ display_name: string; streak_days: number }>(token, "/api/me/profile", {
    method: "PATCH", body: jsonBody({ display_name: displayName }),
  });
  return { displayName: result.display_name, streakDays: result.streak_days };
}

export async function getDashboard(token: string) {
  const result = await backend<{
    display_name: string; streak_days: number; daily_minutes: number;
    daily_target_minutes: number; plan: { id: string; title: string; detail: string; href: string; done: boolean; in_progress: boolean }[];
    completed_count: number; due_count: number; continue_href: string;
    has_active_session: boolean; minutes_by_day: ProgressData["minutesByDay"];
  }>(token, "/api/me/dashboard");
  return {
    displayName: result.display_name,
    streakDays: result.streak_days,
    dailyMinutes: result.daily_minutes,
    dailyTargetMinutes: result.daily_target_minutes,
    plan: result.plan.map((item) => ({ ...item, inProgress: item.in_progress })),
    completedCount: result.completed_count,
    dueCount: result.due_count,
    continueHref: result.continue_href,
    hasActiveSession: result.has_active_session,
    minutesByDay: result.minutes_by_day,
  };
}

export async function getProgress(token: string): Promise<ProgressData> {
  const result = await backend<{
    overall: number; total_attempts: number; has_history: boolean;
    mastery: ProgressData["mastery"];
    minutes_by_day: ProgressData["minutesByDay"];
    practice_days: number;
    next_step: { subject_id: string; topic_id: string; title: string; detail: string; href: string };
  }>(token, "/api/me/progress");
  return {
    overall: result.overall,
    totalAttempts: result.total_attempts,
    hasHistory: result.has_history,
    mastery: result.mastery,
    minutesByDay: result.minutes_by_day,
    practiceDays: result.practice_days,
    nextStep: {
      subjectId: result.next_step.subject_id,
      topicId: result.next_step.topic_id,
      title: result.next_step.title,
      detail: result.next_step.detail,
      href: result.next_step.href,
    },
  };
}

export async function getCatalog(token: string): Promise<{ subjects: LearnerSubject[] }> {
  const result = await backend<{ subjects: {
    id: string; subject_id: string; name: string; mastery: number; attempts: number;
    topic_count: number; topics: { id: string; name: string; approved_question_count: number; attempts: number; mastery: number }[];
  }[] }>(token, "/api/me/catalog");
  return {
    subjects: result.subjects.map((subject) => ({
      id: subject.id,
      subjectId: subject.subject_id,
      name: subject.name,
      mastery: subject.mastery,
      attempts: subject.attempts,
      topicCount: subject.topic_count,
      topics: subject.topics.map((topic) => ({
        id: topic.id,
        name: topic.name,
        approvedQuestionCount: topic.approved_question_count,
        attempts: topic.attempts,
        mastery: topic.mastery,
      })),
    })),
  };
}

export async function getReviewQueue(token: string): Promise<{ cards: ReviewCard[]; dueCount: number }> {
  const result = await backend<{ cards: {
    card_id: string; subject_id: string; topic_id: string; topic: string; prompt: string;
  }[]; due_count: number }>(token, "/api/me/reviews");
  return {
    cards: result.cards.map((card) => ({
      cardId: card.card_id,
      subjectId: card.subject_id,
      topicId: card.topic_id,
      topic: card.topic,
      prompt: card.prompt,
    })),
    dueCount: result.due_count,
  };
}

export async function revealReviewCard(token: string, cardId: string): Promise<Pick<ReviewCard, "answer" | "explanation">> {
  const result = await backend<{ answer: string; explanation: string }>(
    token, `/api/me/reviews/${encodeURIComponent(cardId)}/reveal`, { method: "POST", body: "{}" },
  );
  return { answer: result.answer, explanation: result.explanation };
}

export async function updateReviewCard(token: string, cardId: string, outcome: "got-it" | "again", eventId: string) {
  return backend<{ due_count: number; saved: boolean }>(
    token, `/api/me/reviews/${encodeURIComponent(cardId)}/answer`, {
      method: "POST", body: jsonBody({ outcome, event_id: eventId }),
    },
  );
}

function practiceQuestion(value: Record<string, unknown> | null, subjectId: string, topicId: string): PracticeQuestion | null {
  if (!value || typeof value.id !== "string") return null;
  const rawOptions = Array.isArray(value.options) ? value.options : [];
  const options = rawOptions.map((option, index) => {
    if (typeof option === "string") return { letter: String.fromCharCode(65 + index), text: option };
    if (!option || typeof option !== "object") return null;
    const row = option as Record<string, unknown>;
    const letter = row.letter ?? row.label ?? row.option;
    const text = row.text ?? row.value ?? row.content;
    if (typeof text !== "string") return null;
    return {
      letter: typeof letter === "string" && letter.trim() ? letter.trim() : String.fromCharCode(65 + index),
      text,
    };
  }).filter((option): option is { letter: string; text: string } => option !== null);
  const subject = typeof value.subject === "string" ? value.subject : "Practice";
  const topic = typeof value.topic === "string" ? value.topic : "";
  const context = typeof value.context === "string" ? value.context : "";
  const instructions = typeof value.instructions === "string" ? value.instructions : "";
  const hint = typeof value.hint === "string" ? value.hint : "";
  return {
    id: value.id,
    subjectId,
    topicId,
    subject,
    topic,
    prompt: typeof value.question_text === "string" ? value.question_text : "",
    support: context || instructions,
    hint: hint || "Look for a feature or rule shared by the choices.",
    options,
  };
}

function practiceSession(value: {
  session_id: string; state: string; index: number; total: number;
  current_question: Record<string, unknown> | null; goals?: Record<string, unknown>;
}): PracticeSession {
  const subjectId = typeof value.goals?.plus11_subject_id === "string" ? value.goals.plus11_subject_id : "";
  const topicId = typeof value.goals?.plus11_topic_id === "string" ? value.goals.plus11_topic_id : "";
  return {
    sessionId: value.session_id,
    subjectId,
    topicId,
    questionIndex: value.index,
    totalQuestions: value.total,
    status: value.state,
    question: practiceQuestion(value.current_question, subjectId, topicId),
    state: value.state,
  };
}

export async function createPracticeSession(token: string, subjectId: string, topicId: string, idempotencyKey: string): Promise<PracticeSession> {
  const raw = await backend<Parameters<typeof practiceSession>[0]>(token, "/api/me/practice/sessions", {
    method: "POST",
    body: jsonBody({ subject_id: subjectId, topic_id: topicId, idempotency_key: idempotencyKey }),
  });
  return practiceSession(raw);
}

export async function getPracticeSession(token: string, sessionId: string): Promise<PracticeSession> {
  const raw = await backend<Parameters<typeof practiceSession>[0]>(
    token, `/api/me/practice/sessions/${encodeURIComponent(sessionId)}`,
  );
  return practiceSession(raw);
}

export async function submitPracticeAnswer(token: string, input: {
  sessionId: string; questionId: string; selectedAnswer: string; questionIndex: number;
  idempotencyKey: string; timeTakenMs: number; hintUsed: boolean; action?: "answer" | "retry";
}) {
  const result = await backend<{
    is_correct: boolean; correct_answer?: string; explanation?: string;
    feedback?: { correct_answer?: string; explanation?: string };
    session?: Parameters<typeof practiceSession>[0];
  }>(token, `/api/me/practice/sessions/${encodeURIComponent(input.sessionId)}/answers`, {
    method: "POST",
    body: jsonBody({
      question_id: input.questionId,
      chosen_answer: input.selectedAnswer,
      idempotency_key: input.idempotencyKey,
      time_taken_ms: input.timeTakenMs,
      hint_used: input.hintUsed,
      action: input.action ?? "answer",
    }),
  });
  return {
    isCorrect: result.is_correct,
    correctAnswer: result.correct_answer ?? result.feedback?.correct_answer ?? null,
    explanation: result.explanation ?? result.feedback?.explanation ?? null,
    questionIndex: result.session?.index,
    session: result.session ? practiceSession(result.session) : undefined,
  };
}

export async function retryPracticeQuestion(token: string, sessionId: string) {
  const result = await backend<{ hint: string; session: Parameters<typeof practiceSession>[0] }>(
    token, `/api/me/practice/sessions/${encodeURIComponent(sessionId)}/retry`, {
      method: "POST", body: "{}",
    },
  );
  return { hint: result.hint, session: practiceSession(result.session) };
}

export async function completePracticeSession(token: string, sessionId: string) {
  return backend<Record<string, unknown>>(
    token, `/api/me/practice/sessions/${encodeURIComponent(sessionId)}/complete`, {
      method: "POST", body: "{}",
    },
  );
}

export async function abandonPracticeSession(token: string, sessionId: string) {
  return backend<Record<string, unknown>>(
    token, `/api/me/practice/sessions/${encodeURIComponent(sessionId)}/abandon`, {
      method: "POST", body: "{}",
    },
  );
}
