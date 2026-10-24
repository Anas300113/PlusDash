import "server-only";

import { randomUUID } from "node:crypto";
import type { RowDataPacket } from "mysql2/promise";
import { subjects, type SubjectId } from "@/lib/data";
import { getPool } from "@/lib/db";
import { AppError } from "@/lib/errors";
import { getQuestionForTopicAt, isSupportedSubject, isSupportedTopic } from "@/lib/questions";
import { getPracticeAnswerKey } from "@/lib/question-keys";

export type LearnerProfile = { displayName: string; streakDays: number };

export type ReviewCard = {
  cardId: string;
  subjectId: string;
  topicId: string;
  topic: string;
  prompt: string;
  answer: string;
};

const topicLabels = new Map<string, string>(subjects.flatMap((subject) => subject.topics.map((topic) => [
  `${subject.id}:${topic.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")}`,
  topic,
] as const)));

export function utcDateKey(date = new Date()): string {
  return date.toISOString().slice(0, 10);
}

function shiftDateKey(dateKey: string, offset: number): string {
  const date = new Date(`${dateKey}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return utcDateKey(date);
}

function lastSevenDates(): { date: string; label: string; state: "complete" | "today" | "upcoming" | "missed" }[] {
  const today = new Date();
  const day = today.getUTCDay();
  const mondayOffset = (day + 6) % 7;
  const monday = shiftDateKey(utcDateKey(today), -mondayOffset);
  return Array.from({ length: 7 }, (_, index) => {
    const date = shiftDateKey(monday, index);
    const currentDate = utcDateKey(today);
    const weekday = new Date(`${date}T00:00:00.000Z`).toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" });
    return { date, label: weekday, state: date === currentDate ? "today" : date < currentDate ? "missed" : "upcoming" };
  });
}

async function consecutiveStreak(openId: string): Promise<number> {
  const pool = getPool();
  const [rows] = await pool.execute<RowDataPacket[]>(
    "SELECT activity_date FROM plus11_daily_activity WHERE learner_open_id = ? AND answer_count > 0 ORDER BY activity_date DESC LIMIT 60",
    [openId],
  );
  const dates = rows.map((row) => typeof row.activity_date === "string" ? row.activity_date.slice(0, 10) : utcDateKey(new Date(row.activity_date)));
  let dateToMatch = utcDateKey();
  if (dates[0] !== dateToMatch) dateToMatch = shiftDateKey(dateToMatch, -1);
  let streak = 0;
  for (const date of dates) {
    if (date !== dateToMatch) break;
    streak += 1;
    dateToMatch = shiftDateKey(dateToMatch, -1);
  }
  return streak;
}

export async function ensureLearner(openId: string, providerName: string): Promise<LearnerProfile> {
  const displayName = providerName.trim().slice(0, 80) || "Learner";
  const pool = getPool();
  await pool.execute(
    "INSERT INTO plus11_learners (open_id, display_name) VALUES (?, ?) ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP(3)",
    [openId, displayName],
  );
  const [rows] = await pool.execute<RowDataPacket[]>(
    "SELECT display_name FROM plus11_learners WHERE open_id = ? LIMIT 1",
    [openId],
  );
  const streakDays = await consecutiveStreak(openId);
  return { displayName: rows[0]?.display_name ?? displayName, streakDays };
}

export async function updateLearnerName(openId: string, displayName: string): Promise<LearnerProfile> {
  const normalized = displayName.trim().replace(/\s+/g, " ");
  const length = Array.from(normalized).length;
  if (length < 2 || length > 40 || /[\u0000-\u001f\u007f]/u.test(normalized)) throw new AppError("Use a name between 2 and 40 characters.");
  const pool = getPool();
  await pool.execute(
    "UPDATE plus11_learners SET display_name = ?, updated_at = CURRENT_TIMESTAMP(3) WHERE open_id = ?",
    [normalized, openId],
  );
  const [rows] = await pool.execute<RowDataPacket[]>("SELECT display_name FROM plus11_learners WHERE open_id = ? LIMIT 1", [openId]);
  if (!rows[0]) throw new AppError("We couldn’t find this account. Please sign in again.", 404, "account_not_found");
  return { displayName: rows[0].display_name, streakDays: await consecutiveStreak(openId) };
}

export async function getDashboard(openId: string) {
  const pool = getPool();
  const today = utcDateKey();
  const week = lastSevenDates();
  const [profileRows] = await pool.execute<RowDataPacket[]>("SELECT display_name FROM plus11_learners WHERE open_id = ? LIMIT 1", [openId]);
  const [activityRows] = await pool.execute<RowDataPacket[]>(
    "SELECT activity_date, minutes_practiced, answer_count FROM plus11_daily_activity WHERE learner_open_id = ? AND activity_date BETWEEN ? AND ?",
    [openId, week[0].date, week[6].date],
  );
  const activity = new Map(activityRows.map((row) => [String(row.activity_date).slice(0, 10), row]));
  const minutesByDay = week.map((date) => {
    const row = activity.get(date.date);
    return { ...date, state: row && date.state !== "today" ? "complete" : date.state, minutes: Number(row?.minutes_practiced ?? 0) };
  });
  const todayMinutes = Number(activity.get(today)?.minutes_practiced ?? 0);
  const [planRows] = await pool.execute<RowDataPacket[]>(
    "SELECT activity_id FROM plus11_plan_completions WHERE learner_open_id = ? AND activity_date = ?",
    [openId, today],
  );
  const completed = new Set(planRows.map((row) => String(row.activity_id)));
  const [reviewRows] = await pool.execute<RowDataPacket[]>(
    "SELECT COUNT(*) AS due_count FROM plus11_review_items WHERE learner_open_id = ? AND due_at <= UTC_TIMESTAMP(3)",
    [openId],
  );
  const dueCount = Number(reviewRows[0]?.due_count ?? 0);
  const [activeRows] = await pool.execute<RowDataPacket[]>(
    "SELECT session_id, subject_id, topic_id FROM plus11_practice_sessions WHERE learner_open_id = ? AND status = 'in_progress' AND started_at >= DATE_SUB(UTC_TIMESTAMP(3), INTERVAL 2 DAY) ORDER BY started_at DESC LIMIT 20",
    [openId],
  );
  const active = new Set(activeRows.map((row) => `${row.subject_id}:${row.topic_id}`));
  const continueHref = activeRows[0]
    ? `/practice?subject=${encodeURIComponent(String(activeRows[0].subject_id))}&topic=${encodeURIComponent(String(activeRows[0].topic_id))}`
    : "/practice?subject=verbal-reasoning&topic=odd-one-out";
  const plan = [
    { id: "maths-fractions", title: "Maths: fractions", href: "/learn/maths", done: completed.has("maths-fractions"), inProgress: active.has("maths:fractions"), detail: completed.has("maths-fractions") ? "8 questions, done" : active.has("maths:fractions") ? "Your session is ready to continue" : "8 questions, ready when you are" },
    { id: "verbal-odd-one-out", title: "Verbal reasoning: odd one out", href: "/practice?subject=verbal-reasoning&topic=odd-one-out", done: completed.has("verbal-odd-one-out"), inProgress: active.has("verbal-reasoning:odd-one-out"), detail: completed.has("verbal-odd-one-out") ? "8 questions, done" : active.has("verbal-reasoning:odd-one-out") ? "Your session is ready to continue" : "8 questions, ready when you are" },
    { id: "review", title: `Review: ${dueCount} ${dueCount === 1 ? "card" : "cards"} due`, href: "/review", done: completed.has("review"), inProgress: false, detail: dueCount ? `About ${Math.max(1, Math.round(dueCount * 40 / 60))} minutes` : "No cards due just now" },
  ];
  return {
    displayName: profileRows[0]?.display_name ?? "Learner",
    streakDays: await consecutiveStreak(openId),
    dailyMinutes: todayMinutes,
    dailyTargetMinutes: 30,
    plan,
    completedCount: plan.filter((item) => item.done).length,
    dueCount,
    continueHref,
    minutesByDay,
  };
}

export async function getProgress(openId: string) {
  const pool = getPool();
  const dates = lastSevenDates();
  const [masteryRows] = await pool.execute<RowDataPacket[]>(
    "SELECT subject_id, SUM(attempt_count) AS attempts, SUM(correct_count) AS correct FROM plus11_topic_mastery WHERE learner_open_id = ? GROUP BY subject_id",
    [openId],
  );
  const bySubject = new Map(masteryRows.map((row) => [String(row.subject_id), { attempts: Number(row.attempts), correct: Number(row.correct) }]));
  const mastery = subjects.map((subject) => {
    const row = bySubject.get(subject.id);
    const value = row && row.attempts > 0 ? Math.round(row.correct / row.attempts * 100) : 0;
    return { id: subject.id, name: subject.name, mastery: value, attempts: row?.attempts ?? 0 };
  });
  const totalAttempts = mastery.reduce((sum, item) => sum + item.attempts, 0);
  const correctAttempts = [...bySubject.values()].reduce((sum, item) => sum + item.correct, 0);
  const overall = totalAttempts ? Math.round(correctAttempts / totalAttempts * 100) : 0;
  const [activityRows] = await pool.execute<RowDataPacket[]>(
    "SELECT activity_date, minutes_practiced, answer_count FROM plus11_daily_activity WHERE learner_open_id = ? AND activity_date BETWEEN ? AND ?",
    [openId, dates[0].date, dates[6].date],
  );
  const activity = new Map(activityRows.map((row) => [String(row.activity_date).slice(0, 10), row]));
  const minutesByDay = dates.map((date) => ({
    ...date,
    state: activity.has(date.date) && Number(activity.get(date.date)?.answer_count ?? 0) > 0 && date.state !== "today" ? "complete" : date.state,
    minutes: Number(activity.get(date.date)?.minutes_practiced ?? 0),
  }));
  const practiceDays = activityRows.filter((row) => Number(row.answer_count) > 0).length;
  const [topicRows] = await pool.execute<RowDataPacket[]>(
    "SELECT subject_id, topic_id, attempt_count, correct_count FROM plus11_topic_mastery WHERE learner_open_id = ? AND attempt_count > 0 ORDER BY correct_count / attempt_count ASC, attempt_count DESC LIMIT 1",
    [openId],
  );
  const weakest = topicRows[0];
  const subjectId = weakest ? String(weakest.subject_id) : "maths";
  const topicId = weakest ? String(weakest.topic_id) : "fractions";
  const subject = subjects.find((item) => item.id === subjectId as SubjectId);
  const topic = topicLabels.get(`${subjectId}:${topicId}`) ?? topicId.replaceAll("-", " ");
  return {
    overall,
    totalAttempts,
    mastery,
    minutesByDay,
    practiceDays,
    nextStep: {
      subjectId,
      topicId,
      title: weakest ? `Try ${topic.toLowerCase()} again` : "Choose a topic to begin",
      detail: weakest ? "A short practice can help this topic feel clearer." : "Your progress will start to take shape as you practise.",
      href: `/practice?subject=${subject?.id ?? "maths"}&topic=${encodeURIComponent(topicId)}`,
    },
  };
}

export async function createPracticeSession(openId: string, subjectId: string, topicId: string, idempotencyKey: string) {
  if (!isSupportedSubject(subjectId) || !isSupportedTopic(subjectId, topicId) || !/^[0-9a-f-]{36}$/i.test(idempotencyKey)) {
    throw new AppError("Choose a valid subject and topic before starting practice.");
  }
  const pool = getPool();
  const [openRows] = await pool.execute<RowDataPacket[]>(
    "SELECT session_id, subject_id, topic_id, question_index, total_questions, status FROM plus11_practice_sessions WHERE learner_open_id = ? AND subject_id = ? AND topic_id = ? AND status = 'in_progress' AND started_at >= DATE_SUB(UTC_TIMESTAMP(3), INTERVAL 2 DAY) ORDER BY started_at DESC LIMIT 1",
    [openId, subjectId, topicId],
  );
  if (openRows[0]) {
    return {
      sessionId: String(openRows[0].session_id),
      subjectId: String(openRows[0].subject_id),
      topicId: String(openRows[0].topic_id),
      questionIndex: Number(openRows[0].question_index),
      totalQuestions: Number(openRows[0].total_questions),
      status: String(openRows[0].status),
    };
  }
  const sessionId = randomUUID();
  const activityDate = utcDateKey();
  await pool.execute(
    "INSERT IGNORE INTO plus11_practice_sessions (session_id, learner_open_id, idempotency_key, subject_id, topic_id, activity_date, total_questions) VALUES (?, ?, ?, ?, ?, ?, 8)",
    [sessionId, openId, idempotencyKey, subjectId, topicId, activityDate],
  );
  const [rows] = await pool.execute<RowDataPacket[]>(
    "SELECT session_id, subject_id, topic_id, question_index, total_questions, status FROM plus11_practice_sessions WHERE learner_open_id = ? AND idempotency_key = ? LIMIT 1",
    [openId, idempotencyKey],
  );
  if (!rows[0]) throw new AppError("We couldn’t start this practice session. Please try again.");
  return {
    sessionId: String(rows[0].session_id),
    subjectId: String(rows[0].subject_id),
    topicId: String(rows[0].topic_id),
    questionIndex: Number(rows[0].question_index),
    totalQuestions: Number(rows[0].total_questions),
    status: String(rows[0].status),
  };
}

export async function submitPracticeAnswer(openId: string, input: { sessionId: string; questionId: string; selectedAnswer: string; questionIndex: number; idempotencyKey: string }) {
  if (!/^[0-9a-f-]{36}$/i.test(input.sessionId) || !/^[0-9a-f-]{36}$/i.test(input.idempotencyKey) || !Number.isInteger(input.questionIndex) || input.questionIndex < 0 || input.questionIndex > 7) {
    throw new AppError("This practice answer could not be checked. Please try again.");
  }
  const pool = getPool();
  const connection = await pool.getConnection();
  try {
    await connection.beginTransaction();
    const [duplicateRows] = await connection.execute<RowDataPacket[]>(
      "SELECT is_correct, question_index, question_id FROM plus11_practice_answers WHERE learner_open_id = ? AND idempotency_key = ? LIMIT 1",
      [openId, input.idempotencyKey],
    );
    if (duplicateRows[0]) {
      await connection.commit();
      const isCorrect = Boolean(duplicateRows[0].is_correct);
      const answerKey = getPracticeAnswerKey(String(duplicateRows[0].question_id));
      return { isCorrect, questionIndex: Number(duplicateRows[0].question_index), explanation: isCorrect ? answerKey?.explanation ?? null : null };
    }
    const [sessionRows] = await connection.execute<RowDataPacket[]>(
      "SELECT session_id, subject_id, topic_id, question_index, total_questions, status, activity_date FROM plus11_practice_sessions WHERE session_id = ? AND learner_open_id = ? FOR UPDATE",
      [input.sessionId, openId],
    );
    const session = sessionRows[0];
    if (!session || session.status !== "in_progress") throw new AppError("This practice session has ended. Start a new one to keep learning.", 409, "session_ended");
    const expectedIndex = Number(session.question_index);
    if (expectedIndex !== input.questionIndex || expectedIndex >= Number(session.total_questions)) throw new AppError("This question has changed. Refresh the practice screen and try again.", 409, "question_changed");
    const question = getQuestionForTopicAt(String(session.subject_id), String(session.topic_id), expectedIndex);
    const answerKey = question ? getPracticeAnswerKey(question.id) : undefined;
    if (!question || !answerKey || question.id !== input.questionId || !question.options.some((option) => option.letter === input.selectedAnswer)) {
      throw new AppError("This answer doesn’t match the current question. Please refresh and try again.");
    }
    const [attemptRows] = await connection.execute<RowDataPacket[]>(
      "SELECT COUNT(*) AS attempts, MAX(is_correct) AS already_correct FROM plus11_practice_answers WHERE session_id = ? AND question_index = ?",
      [input.sessionId, expectedIndex],
    );
    if (Boolean(attemptRows[0]?.already_correct)) throw new AppError("This question has already been answered correctly.");
    const attemptNumber = Number(attemptRows[0]?.attempts ?? 0) + 1;
    const isCorrect = input.selectedAnswer === answerKey.answer;
    await connection.execute(
      "INSERT INTO plus11_practice_answers (session_id, learner_open_id, question_id, subject_id, topic_id, question_index, attempt_number, idempotency_key, selected_answer, is_correct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      [input.sessionId, openId, question.id, question.subjectId, question.topicId, expectedIndex, attemptNumber, input.idempotencyKey, input.selectedAnswer, isCorrect ? 1 : 0],
    );
    await connection.execute(
      "INSERT INTO plus11_topic_mastery (learner_open_id, subject_id, topic_id, attempt_count, correct_count, last_practiced_at) VALUES (?, ?, ?, 1, ?, UTC_TIMESTAMP(3)) ON DUPLICATE KEY UPDATE attempt_count = attempt_count + 1, correct_count = correct_count + VALUES(correct_count), last_practiced_at = UTC_TIMESTAMP(3)",
      [openId, question.subjectId, question.topicId, isCorrect ? 1 : 0],
    );
    if (isCorrect) {
      await connection.execute("UPDATE plus11_practice_sessions SET question_index = question_index + 1 WHERE session_id = ? AND learner_open_id = ?", [input.sessionId, openId]);
    } else {
      await connection.execute(
        "INSERT INTO plus11_review_items (card_id, learner_open_id, source_question_id, subject_id, topic_id, prompt, answer, due_at) VALUES (?, ?, ?, ?, ?, ?, ?, UTC_TIMESTAMP(3)) ON DUPLICATE KEY UPDATE due_at = LEAST(due_at, VALUES(due_at))",
        [randomUUID(), openId, question.id, question.subjectId, question.topicId, question.prompt, answerKey.explanation],
      );
    }
    const activityDate = String(session.activity_date).slice(0, 10);
    const [durationRows] = await connection.execute<RowDataPacket[]>(
      "SELECT COALESCE(SUM(duration_seconds), 0) AS total_seconds FROM plus11_practice_sessions WHERE learner_open_id = ? AND activity_date = ?",
      [openId, activityDate],
    );
    await connection.execute(
      "UPDATE plus11_practice_sessions SET duration_seconds = GREATEST(duration_seconds, TIMESTAMPDIFF(SECOND, started_at, UTC_TIMESTAMP(3))) WHERE session_id = ? AND learner_open_id = ?",
      [input.sessionId, openId],
    );
    const [updatedDurationRows] = await connection.execute<RowDataPacket[]>(
      "SELECT COALESCE(SUM(duration_seconds), 0) AS total_seconds FROM plus11_practice_sessions WHERE learner_open_id = ? AND activity_date = ?",
      [openId, activityDate],
    );
    const priorSeconds = Number(durationRows[0]?.total_seconds ?? 0);
    const totalSeconds = Number(updatedDurationRows[0]?.total_seconds ?? 0);
    await connection.execute(
      "INSERT INTO plus11_daily_activity (learner_open_id, activity_date, minutes_practiced, answer_count, correct_count) VALUES (?, ?, ?, 1, ?) ON DUPLICATE KEY UPDATE minutes_practiced = GREATEST(minutes_practiced, VALUES(minutes_practiced)), answer_count = answer_count + 1, correct_count = correct_count + VALUES(correct_count)",
    [openId, activityDate, Math.ceil(Math.max(priorSeconds, totalSeconds) / 60), isCorrect ? 1 : 0],
    );
    await connection.commit();
    return { isCorrect, questionIndex: expectedIndex, explanation: isCorrect ? answerKey.explanation : null };
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}

export async function completePracticeSession(openId: string, sessionId: string) {
  if (!/^[0-9a-f-]{36}$/i.test(sessionId)) throw new AppError("This practice session couldn’t be completed.", 400, "invalid_session");
  const pool = getPool();
  const connection = await pool.getConnection();
  try {
    await connection.beginTransaction();
    const [rows] = await connection.execute<RowDataPacket[]>(
      "SELECT subject_id, topic_id, question_index, total_questions, status, activity_date FROM plus11_practice_sessions WHERE session_id = ? AND learner_open_id = ? FOR UPDATE",
      [sessionId, openId],
    );
    const session = rows[0];
    if (!session) throw new AppError("We couldn’t find that practice session.", 404, "session_not_found");
    if (session.status !== "completed") {
      if (Number(session.question_index) < Number(session.total_questions)) throw new AppError("Finish the remaining questions before closing this session.");
      await connection.execute("UPDATE plus11_practice_sessions SET status = 'completed', completed_at = UTC_TIMESTAMP(3) WHERE session_id = ? AND learner_open_id = ?", [sessionId, openId]);
      const subjectId = String(session.subject_id);
      const topicId = String(session.topic_id);
      const activityId = subjectId === "maths" && topicId === "fractions" ? "maths-fractions" : subjectId === "verbal-reasoning" && topicId === "odd-one-out" ? "verbal-odd-one-out" : null;
      if (activityId) {
        await connection.execute(
          "INSERT IGNORE INTO plus11_plan_completions (learner_open_id, activity_date, activity_id) VALUES (?, ?, ?)",
          [openId, String(session.activity_date).slice(0, 10), activityId],
        );
      }
    }
    await connection.commit();
    return { completed: true };
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}

export async function listDueReviewCards(openId: string): Promise<ReviewCard[]> {
  const pool = getPool();
  const [rows] = await pool.execute<RowDataPacket[]>(
    "SELECT card_id, subject_id, topic_id, prompt, answer FROM plus11_review_items WHERE learner_open_id = ? AND due_at <= UTC_TIMESTAMP(3) ORDER BY due_at ASC, created_at ASC",
    [openId],
  );
  return rows.map((row) => {
    const subjectId = String(row.subject_id);
    const topicId = String(row.topic_id);
    return {
      cardId: String(row.card_id),
      subjectId,
      topicId,
      topic: topicLabels.get(`${subjectId}:${topicId}`) ?? topicId.replaceAll("-", " "),
      prompt: String(row.prompt),
      answer: String(row.answer),
    };
  });
}

export async function recordReviewOutcome(openId: string, cardId: string, outcome: "got-it" | "again", eventId: string) {
  if (!/^[0-9a-f-]{36}$/i.test(cardId) || !/^[0-9a-f-]{36}$/i.test(eventId)) throw new AppError("This review action couldn’t be saved.");
  const pool = getPool();
  const connection = await pool.getConnection();
  try {
    await connection.beginTransaction();
    const [rows] = await connection.execute<RowDataPacket[]>(
      "SELECT card_id, last_event_id FROM plus11_review_items WHERE card_id = ? AND learner_open_id = ? FOR UPDATE",
      [cardId, openId],
    );
    if (!rows[0]) throw new AppError("This review card is no longer available.", 404, "review_card_not_found");
    if (String(rows[0].last_event_id ?? "") !== eventId) {
      await connection.execute(
        "UPDATE plus11_review_items SET last_reviewed_at = UTC_TIMESTAMP(3), review_count = review_count + 1, correct_streak = IF(?, correct_streak + 1, 0), last_outcome = ?, last_event_id = ?, due_at = DATE_ADD(UTC_TIMESTAMP(3), INTERVAL ? DAY) WHERE card_id = ? AND learner_open_id = ?",
        [outcome === "got-it" ? 1 : 0, outcome, eventId, outcome === "got-it" ? 3 : 1, cardId, openId],
      );
    }
    const [dueRows] = await connection.execute<RowDataPacket[]>(
      "SELECT COUNT(*) AS due_count FROM plus11_review_items WHERE learner_open_id = ? AND due_at <= UTC_TIMESTAMP(3)",
      [openId],
    );
    const dueCount = Number(dueRows[0]?.due_count ?? 0);
    if (dueCount === 0) {
      await connection.execute(
        "INSERT IGNORE INTO plus11_plan_completions (learner_open_id, activity_date, activity_id) VALUES (?, UTC_DATE(), 'review')",
        [openId],
      );
    }
    await connection.commit();
    return { dueCount };
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}
