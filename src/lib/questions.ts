import type { SubjectId } from "@/lib/data";

export type PracticeOption = { letter: string; text: string };

/** Public question content only. Correct answers and explanations live server-side. */
export type PracticeQuestion = {
  id: string;
  subjectId: SubjectId;
  topicId: string;
  subject: string;
  prompt: string;
  support: string;
  hint: string;
  options: PracticeOption[];
};

const questionSets: Record<SubjectId, PracticeQuestion[]> = {
  "verbal-reasoning": [
    { id: "vr-odd-one-out-01", subjectId: "verbal-reasoning", topicId: "odd-one-out", subject: "Verbal reasoning, odd one out", prompt: "Which word is the odd one out?", support: "Think about what the others have in common.", hint: "Three of these instruments make sound with vibrating strings.", options: [{ letter: "A", text: "Violin" }, { letter: "B", text: "Trumpet" }, { letter: "C", text: "Cello" }, { letter: "D", text: "Harp" }] },
    { id: "vr-word-links-01", subjectId: "verbal-reasoning", topicId: "word-links", subject: "Verbal reasoning, word links", prompt: "Which word completes the pair?", support: "Bird is to nest as bee is to …", hint: "Think of the place where a group of bees lives.", options: [{ letter: "A", text: "Hive" }, { letter: "B", text: "Web" }, { letter: "C", text: "Burrow" }, { letter: "D", text: "Den" }] },
    { id: "vr-letter-sequences-01", subjectId: "verbal-reasoning", topicId: "letter-sequences", subject: "Verbal reasoning, letter sequences", prompt: "What letter comes next?", support: "A, C, E, G, …", hint: "Count how many letters you skip each time.", options: [{ letter: "A", text: "H" }, { letter: "B", text: "I" }, { letter: "C", text: "J" }, { letter: "D", text: "K" }] },
    { id: "vr-code-words-01", subjectId: "verbal-reasoning", topicId: "code-words", subject: "Verbal reasoning, code words", prompt: "Which word means the opposite of ‘ancient’?", support: "Look for a word that describes something very new.", hint: "This word can describe a newly built house.", options: [{ letter: "A", text: "Old" }, { letter: "B", text: "Modern" }, { letter: "C", text: "Historic" }, { letter: "D", text: "Earlier" }] },
  ],
  "non-verbal-reasoning": [
    { id: "nvr-rotations-01", subjectId: "non-verbal-reasoning", topicId: "rotations", subject: "Non-verbal reasoning, rotations", prompt: "A shape turns a quarter turn clockwise. How far has it turned?", support: "A full turn is 360 degrees.", hint: "A quarter is one of four equal parts of a full turn.", options: [{ letter: "A", text: "45 degrees" }, { letter: "B", text: "90 degrees" }, { letter: "C", text: "180 degrees" }, { letter: "D", text: "360 degrees" }] },
    { id: "nvr-shape-sequences-01", subjectId: "non-verbal-reasoning", topicId: "shape-sequences", subject: "Non-verbal reasoning, shape sequences", prompt: "A pattern goes circle, diamond, circle, diamond. What comes next?", support: "Look for the part of the pattern that repeats.", hint: "The two shapes take turns appearing.", options: [{ letter: "A", text: "Circle" }, { letter: "B", text: "Diamond" }, { letter: "C", text: "Triangle" }, { letter: "D", text: "Square" }] },
    { id: "nvr-reflections-01", subjectId: "non-verbal-reasoning", topicId: "reflections", subject: "Non-verbal reasoning, reflections", prompt: "A left-pointing arrow is reflected in a vertical mirror. Which way does it point?", support: "A reflection flips the image across the mirror line.", hint: "Imagine the arrow facing its mirror image.", options: [{ letter: "A", text: "Left" }, { letter: "B", text: "Right" }, { letter: "C", text: "Up" }, { letter: "D", text: "Down" }] },
    { id: "nvr-missing-shapes-01", subjectId: "non-verbal-reasoning", topicId: "missing-shapes", subject: "Non-verbal reasoning, missing shapes", prompt: "Which shape completes the pattern? Circle, diamond, circle, diamond, …", support: "Check which two shapes alternate.", hint: "The first and third shapes match.", options: [{ letter: "A", text: "Diamond" }, { letter: "B", text: "Circle" }, { letter: "C", text: "Square" }, { letter: "D", text: "Triangle" }] },
  ],
  maths: [
    { id: "maths-fractions-01", subjectId: "maths", topicId: "fractions", subject: "Maths, fractions", prompt: "What is 1/2 + 1/4?", support: "Try giving both fractions the same denominator.", hint: "One half is the same as two quarters.", options: [{ letter: "A", text: "2/6" }, { letter: "B", text: "3/4" }, { letter: "C", text: "1/6" }, { letter: "D", text: "2/4" }] },
    { id: "maths-number-sequences-01", subjectId: "maths", topicId: "number-sequences", subject: "Maths, number sequences", prompt: "What number comes next?", support: "6, 9, 12, …", hint: "Compare each number with the one before it.", options: [{ letter: "A", text: "13" }, { letter: "B", text: "14" }, { letter: "C", text: "15" }, { letter: "D", text: "16" }] },
    { id: "maths-ratio-and-proportion-01", subjectId: "maths", topicId: "ratio-and-proportion", subject: "Maths, ratio and proportion", prompt: "Red and blue counters are in the ratio 2:3. If there are 4 red counters, how many blue counters are there?", support: "The red amount has doubled from 2 to 4.", hint: "Keep the same scale for the blue amount too.", options: [{ letter: "A", text: "4" }, { letter: "B", text: "5" }, { letter: "C", text: "6" }, { letter: "D", text: "8" }] },
    { id: "maths-area-and-perimeter-01", subjectId: "maths", topicId: "area-and-perimeter", subject: "Maths, area and perimeter", prompt: "A rectangle is 5 cm long and 3 cm wide. What is its perimeter?", support: "Perimeter is the distance all the way around the shape.", hint: "Add all four sides: 5 + 3 + 5 + 3.", options: [{ letter: "A", text: "8 cm" }, { letter: "B", text: "13 cm" }, { letter: "C", text: "15 cm" }, { letter: "D", text: "16 cm" }] },
  ],
  english: [
    { id: "english-vocabulary-01", subjectId: "english", topicId: "vocabulary", subject: "English, vocabulary", prompt: "Which word means the opposite of ‘ancient’?", support: "Look for a word that describes something very new.", hint: "This word can describe a newly built house.", options: [{ letter: "A", text: "Old" }, { letter: "B", text: "Modern" }, { letter: "C", text: "Historic" }, { letter: "D", text: "Earlier" }] },
    { id: "english-comprehension-01", subjectId: "english", topicId: "comprehension", subject: "English, comprehension", prompt: "Mia hurried indoors when the first drops fell. What was the weather doing?", support: "Use the clue in the sentence to work it out.", hint: "The word ‘drops’ tells you what was falling.", options: [{ letter: "A", text: "It was starting to rain" }, { letter: "B", text: "The wind had stopped" }, { letter: "C", text: "It was getting warmer" }, { letter: "D", text: "It had started to snow" }] },
    { id: "english-spelling-patterns-01", subjectId: "english", topicId: "spelling-patterns", subject: "English, spelling patterns", prompt: "Which word is spelled correctly?", support: "Look closely at the letters in each choice.", hint: "The word has one ‘c’ and two ‘s’ letters.", options: [{ letter: "A", text: "Neccessary" }, { letter: "B", text: "Necesary" }, { letter: "C", text: "Necessary" }, { letter: "D", text: "Necessay" }] },
    { id: "english-sentence-meaning-01", subjectId: "english", topicId: "sentence-meaning", subject: "English, sentence meaning", prompt: "If someone feels ‘under the weather’, how are they probably feeling?", support: "This phrase has a meaning beyond the words themselves.", hint: "It’s a gentle way to say they don’t feel well.", options: [{ letter: "A", text: "Excited" }, { letter: "B", text: "Unwell" }, { letter: "C", text: "Sleepy" }, { letter: "D", text: "Proud" }] },
  ],
};

const topicOrder: Record<SubjectId, string[]> = {
  maths: ["fractions", "number-sequences", "ratio-and-proportion", "area-and-perimeter"],
  english: ["vocabulary", "comprehension", "spelling-patterns", "sentence-meaning"],
  "verbal-reasoning": ["odd-one-out", "word-links", "letter-sequences", "code-words"],
  "non-verbal-reasoning": ["rotations", "shape-sequences", "reflections", "missing-shapes"],
};

export function isSupportedSubject(value: string): value is SubjectId {
  return Object.hasOwn(topicOrder, value);
}

export function isSupportedTopic(subjectId: string, topicId: string): boolean {
  return isSupportedSubject(subjectId) && topicOrder[subjectId].includes(topicId);
}

export function getQuestionsForTopic(subjectId: string, topicId: string): PracticeQuestion[] {
  if (!isSupportedSubject(subjectId) || !topicOrder[subjectId].includes(topicId)) return [];
  const questions = questionSets[subjectId];
  const index = topicOrder[subjectId].indexOf(topicId);
  return [...questions.slice(index), ...questions.slice(0, index)];
}

export function getQuestionForTopicAt(subjectId: string, topicId: string, index: number): PracticeQuestion | undefined {
  const questions = getQuestionsForTopic(subjectId, topicId);
  return questions.length ? questions[index % questions.length] : undefined;
}

export function getQuestionById(questionId: string): PracticeQuestion | undefined {
  return Object.values(questionSets).flat().find((question) => question.id === questionId);
}

export function getQuestionSetLength(subjectId: string, topicId: string): number {
  return getQuestionsForTopic(subjectId, topicId).length;
}
