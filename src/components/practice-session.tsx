"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Check, Clock3, Lightbulb, X } from "lucide-react";

type Question = {
  subject: string;
  prompt: string;
  support: string;
  hint: string;
  options: { letter: string; text: string }[];
  answer: string;
  explanation: string;
};

const verbalQuestions: Question[] = [
  {
    subject: "Verbal reasoning, odd one out",
    prompt: "Which word is the odd one out?",
    support: "Think about what the others have in common.",
    hint: "Three of these instruments make sound with vibrating strings.",
    options: [
      { letter: "A", text: "Violin" },
      { letter: "B", text: "Trumpet" },
      { letter: "C", text: "Cello" },
      { letter: "D", text: "Harp" },
    ],
    answer: "B",
    explanation: "Violin, cello, and harp are string instruments. A trumpet is a brass instrument, so it is the odd one out.",
  },
  {
    subject: "Verbal reasoning, word links",
    prompt: "Which word completes the pair?",
    support: "Bird is to nest as bee is to …",
    hint: "Think of the place where a group of bees lives.",
    options: [
      { letter: "A", text: "Hive" },
      { letter: "B", text: "Web" },
      { letter: "C", text: "Burrow" },
      { letter: "D", text: "Den" },
    ],
    answer: "A",
    explanation: "A bird lives in a nest and a group of bees lives in a hive.",
  },
  {
    subject: "Verbal reasoning, letter sequences",
    prompt: "What letter comes next?",
    support: "A, C, E, G, …",
    hint: "Count how many letters you skip each time.",
    options: [
      { letter: "A", text: "H" },
      { letter: "B", text: "I" },
      { letter: "C", text: "J" },
      { letter: "D", text: "K" },
    ],
    answer: "B",
    explanation: "The sequence skips one letter each time: A, C, E, G, then I.",
  },
  {
    subject: "Verbal reasoning, word meaning",
    prompt: "Which word means the opposite of ‘ancient’?",
    support: "Look for a word that describes something very new.",
    hint: "This word can describe a newly built house.",
    options: [
      { letter: "A", text: "Old" },
      { letter: "B", text: "Modern" },
      { letter: "C", text: "Historic" },
      { letter: "D", text: "Earlier" },
    ],
    answer: "B",
    explanation: "Modern means recent or up to date, so it is the opposite of ancient.",
  },
];

const rotationQuestions: Question[] = [
  {
    subject: "Non-verbal reasoning, rotations",
    prompt: "A shape turns a quarter turn clockwise. How far has it turned?",
    support: "A full turn is 360 degrees.",
    hint: "A quarter is one of four equal parts of a full turn.",
    options: [
      { letter: "A", text: "45 degrees" },
      { letter: "B", text: "90 degrees" },
      { letter: "C", text: "180 degrees" },
      { letter: "D", text: "360 degrees" },
    ],
    answer: "B",
    explanation: "A quarter turn is one of four equal parts of a full 360-degree turn: 360 ÷ 4 = 90 degrees.",
  },
  {
    subject: "Non-verbal reasoning, shape sequences",
    prompt: "A pattern goes circle, diamond, circle, diamond. What comes next?",
    support: "Look for the part of the pattern that repeats.",
    hint: "The two shapes take turns appearing.",
    options: [{ letter: "A", text: "Circle" }, { letter: "B", text: "Diamond" }, { letter: "C", text: "Triangle" }, { letter: "D", text: "Square" }],
    answer: "A",
    explanation: "The pattern alternates between a circle and a diamond, so the next shape is a circle.",
  },
  {
    subject: "Non-verbal reasoning, reflections",
    prompt: "A left-pointing arrow is reflected in a vertical mirror. Which way does it point?",
    support: "A reflection flips the image across the mirror line.",
    hint: "Imagine the arrow facing its mirror image.",
    options: [{ letter: "A", text: "Left" }, { letter: "B", text: "Right" }, { letter: "C", text: "Up" }, { letter: "D", text: "Down" }],
    answer: "B",
    explanation: "A vertical mirror flips left and right, so the reflected arrow points right.",
  },
  {
    subject: "Non-verbal reasoning, missing shapes",
    prompt: "Which shape completes the pattern? Circle, diamond, circle, diamond, …",
    support: "Check which two shapes alternate.",
    hint: "The first and third shapes match.",
    options: [{ letter: "A", text: "Diamond" }, { letter: "B", text: "Circle" }, { letter: "C", text: "Square" }, { letter: "D", text: "Triangle" }],
    answer: "B",
    explanation: "Circle and diamond alternate, so a circle comes next.",
  },
];

const mathsQuestions: Question[] = [
  {
    subject: "Maths, fractions",
    prompt: "What is 1/2 + 1/4?",
    support: "Try giving both fractions the same denominator.",
    hint: "One half is the same as two quarters.",
    options: [
      { letter: "A", text: "2/6" },
      { letter: "B", text: "3/4" },
      { letter: "C", text: "1/6" },
      { letter: "D", text: "2/4" },
    ],
    answer: "B",
    explanation: "One half is 2/4. Then 2/4 + 1/4 = 3/4.",
  },
  {
    subject: "Maths, number sequences",
    prompt: "What number comes next?",
    support: "6, 9, 12, …",
    hint: "Compare each number with the one before it.",
    options: [{ letter: "A", text: "13" }, { letter: "B", text: "14" }, { letter: "C", text: "15" }, { letter: "D", text: "16" }],
    answer: "C",
    explanation: "The sequence adds 3 each time, so 12 + 3 = 15.",
  },
  {
    subject: "Maths, ratio and proportion",
    prompt: "Red and blue counters are in the ratio 2:3. If there are 4 red counters, how many blue counters are there?",
    support: "The red amount has doubled from 2 to 4.",
    hint: "Keep the same scale for the blue amount too.",
    options: [{ letter: "A", text: "4" }, { letter: "B", text: "5" }, { letter: "C", text: "6" }, { letter: "D", text: "8" }],
    answer: "C",
    explanation: "The red amount doubled, so double 3 blue counters as well: 3 × 2 = 6.",
  },
  {
    subject: "Maths, area and perimeter",
    prompt: "A rectangle is 5 cm long and 3 cm wide. What is its perimeter?",
    support: "Perimeter is the distance all the way around the shape.",
    hint: "Add all four sides: 5 + 3 + 5 + 3.",
    options: [{ letter: "A", text: "8 cm" }, { letter: "B", text: "13 cm" }, { letter: "C", text: "15 cm" }, { letter: "D", text: "16 cm" }],
    answer: "D",
    explanation: "A rectangle has two sides of each length: 5 + 3 + 5 + 3 = 16 cm.",
  },
];

const englishQuestions: Question[] = [
  {
    subject: "English, vocabulary",
    prompt: "Which word means the opposite of ‘ancient’?",
    support: "Look for a word that describes something very new.",
    hint: "This word can describe a newly built house.",
    options: [
      { letter: "A", text: "Old" },
      { letter: "B", text: "Modern" },
      { letter: "C", text: "Historic" },
      { letter: "D", text: "Earlier" },
    ],
    answer: "B",
    explanation: "Modern means recent or up to date, so it is the opposite of ancient.",
  },
  {
    subject: "English, comprehension",
    prompt: "Mia hurried indoors when the first drops fell. What was the weather doing?",
    support: "Use the clue in the sentence to work it out.",
    hint: "The word ‘drops’ tells you what was falling.",
    options: [{ letter: "A", text: "It was starting to rain" }, { letter: "B", text: "The wind had stopped" }, { letter: "C", text: "It was getting warmer" }, { letter: "D", text: "It had started to snow" }],
    answer: "A",
    explanation: "The first drops falling suggest that it was beginning to rain.",
  },
  {
    subject: "English, spelling patterns",
    prompt: "Which word is spelled correctly?",
    support: "Look closely at the letters in each choice.",
    hint: "The word has one ‘c’ and two ‘s’ letters.",
    options: [{ letter: "A", text: "Neccessary" }, { letter: "B", text: "Necesary" }, { letter: "C", text: "Necessary" }, { letter: "D", text: "Necessay" }],
    answer: "C",
    explanation: "Necessary is spelled n-e-c-e-s-s-a-r-y.",
  },
  {
    subject: "English, sentence meaning",
    prompt: "If someone feels ‘under the weather’, how are they probably feeling?",
    support: "This phrase has a meaning beyond the words themselves.",
    hint: "It’s a gentle way to say they don’t feel well.",
    options: [{ letter: "A", text: "Excited" }, { letter: "B", text: "Unwell" }, { letter: "C", text: "Sleepy" }, { letter: "D", text: "Proud" }],
    answer: "B",
    explanation: "‘Under the weather’ is an expression that means feeling a little unwell.",
  },
];

const questionSets: Record<string, Question[]> = {
  maths: mathsQuestions,
  english: englishQuestions,
  "verbal-reasoning": verbalQuestions,
  "non-verbal-reasoning": rotationQuestions,
};

const topicPositions: Record<string, Record<string, number>> = {
  maths: { fractions: 0, "number-sequences": 1, "ratio-and-proportion": 2, "area-and-perimeter": 3 },
  english: { vocabulary: 0, comprehension: 1, "spelling-patterns": 2, "sentence-meaning": 3 },
  "verbal-reasoning": { "odd-one-out": 0, "word-links": 1, "letter-sequences": 2, "code-words": 3 },
  "non-verbal-reasoning": { rotations: 0, "shape-sequences": 1, reflections: 2, "missing-shapes": 3 },
};

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function PracticeSession() {
  const searchParams = useSearchParams();
  const selectedSubject = searchParams.get("subject") ?? "verbal-reasoning";
  const selectedTopic = searchParams.get("topic") ?? "";
  const baseQuestions = questionSets[selectedSubject] ?? verbalQuestions;
  const startIndex = topicPositions[selectedSubject]?.[selectedTopic] ?? 0;
  const questionSet = [...baseQuestions.slice(startIndex), ...baseQuestions.slice(0, startIndex)];
  const [questionIndex, setQuestionIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [hintVisible, setHintVisible] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [elapsed, setElapsed] = useState(42);
  const [complete, setComplete] = useState(false);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();
  const current = questionSet[questionIndex];
  const step = 5 + questionIndex;
  const isCorrect = selected === current.answer;

  useEffect(() => {
    if (submitted || complete) return;
    const timer = window.setInterval(() => setElapsed((seconds) => seconds + 1), 1000);
    return () => window.clearInterval(timer);
  }, [submitted, complete, questionIndex]);

  useEffect(() => {
    if (submitted) feedbackRef.current?.focus();
  }, [submitted]);

  function checkAnswer() {
    if (!selected) return;
    setSubmitted(true);
  }

  function tryAgain() {
    setSubmitted(false);
    setSelected(null);
  }

  function nextQuestion() {
    if (step >= 8) {
      setComplete(true);
      return;
    }
    setQuestionIndex((index) => Math.min(index + 1, questionSet.length - 1));
    setSelected(null);
    setHintVisible(false);
    setSubmitted(false);
    setElapsed(42);
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
        <span className="session-clock"><Clock3 size={17} strokeWidth={2} aria-hidden="true" /> {formatTime(elapsed)}</span>
      </header>

      <div className="practice-body">
        <div className="practice-context">
          <span>{current.subject}</span>
          <span>{step} of 8</span>
        </div>

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

        <fieldset className="answer-fieldset" disabled={submitted}>
          <legend className="sr-only">Choose one answer</legend>
          <div className="answer-list">
            {current.options.map(({ letter, text }) => (
              <label className={`answer-option${selected === letter ? " is-selected" : ""}`} key={letter}>
                <input
                  type="radio"
                  name="practice-answer"
                  value={letter}
                  checked={selected === letter}
                  onChange={() => setSelected(letter)}
                  aria-label={`${letter}: ${text}`}
                />
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
              <motion.p
                key="hint"
                className="hint-message"
                initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0, y: -2 }}
                transition={{ duration: reduceMotion ? 0 : 0.18 }}
              >
                <Lightbulb size={18} aria-hidden="true" /><span><strong>A little hint</strong>{current.hint}</span>
              </motion.p>
            ) : null}
          </AnimatePresence>

          {submitted ? (
            <div className={`answer-feedback${isCorrect ? " feedback-correct" : " feedback-try-again"}`} ref={feedbackRef} tabIndex={-1} role="status" aria-live="polite">
              <span className="feedback-icon" aria-hidden="true">{isCorrect ? <Check size={18} strokeWidth={2.5} /> : <Lightbulb size={18} />}</span>
              <div className="feedback-copy">
                <strong>{isCorrect ? "That’s right." : "Not quite yet."}</strong>
                <p>{isCorrect ? current.explanation : "Have another look at the hint above, then try a different answer."}</p>
              </div>
              {isCorrect ? (
                <button className="button button-primary feedback-action" onClick={nextQuestion}>{step >= 8 ? "Finish" : "Continue"} <ArrowRight size={16} aria-hidden="true" /></button>
              ) : (
                <button className="button button-secondary feedback-action" onClick={tryAgain}>Try again</button>
              )}
            </div>
          ) : (
            <div className="practice-actions">
              <button className={`button button-secondary hint-button${hintVisible ? " is-open" : ""}`} onClick={() => setHintVisible((visible) => !visible)} aria-expanded={hintVisible}>
                <Lightbulb size={17} strokeWidth={2} aria-hidden="true" /> {hintVisible ? "Hide hint" : "Hint"}
              </button>
              <button className="button button-primary check-button" onClick={checkAnswer} disabled={!selected}>
                Check answer <ArrowRight size={17} aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
