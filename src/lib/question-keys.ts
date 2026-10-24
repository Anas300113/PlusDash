import "server-only";

export type PracticeAnswerKey = { answer: string; explanation: string };

const answerKeys: Record<string, PracticeAnswerKey> = {
  "vr-odd-one-out-01": { answer: "B", explanation: "Violin, cello, and harp are string instruments. A trumpet is a brass instrument, so it is the odd one out." },
  "vr-word-links-01": { answer: "A", explanation: "A bird lives in a nest and a group of bees lives in a hive." },
  "vr-letter-sequences-01": { answer: "B", explanation: "The sequence skips one letter each time: A, C, E, G, then I." },
  "vr-code-words-01": { answer: "B", explanation: "Modern means recent or up to date, so it is the opposite of ancient." },
  "nvr-rotations-01": { answer: "B", explanation: "A quarter turn is one of four equal parts of a full 360-degree turn: 360 ÷ 4 = 90 degrees." },
  "nvr-shape-sequences-01": { answer: "A", explanation: "The pattern alternates between a circle and a diamond, so the next shape is a circle." },
  "nvr-reflections-01": { answer: "B", explanation: "A vertical mirror flips left and right, so the reflected arrow points right." },
  "nvr-missing-shapes-01": { answer: "B", explanation: "Circle and diamond alternate, so a circle comes next." },
  "maths-fractions-01": { answer: "B", explanation: "One half is 2/4. Then 2/4 + 1/4 = 3/4." },
  "maths-number-sequences-01": { answer: "C", explanation: "The sequence adds 3 each time, so 12 + 3 = 15." },
  "maths-ratio-and-proportion-01": { answer: "C", explanation: "The red amount doubled, so double 3 blue counters as well: 3 × 2 = 6." },
  "maths-area-and-perimeter-01": { answer: "D", explanation: "A rectangle has two sides of each length: 5 + 3 + 5 + 3 = 16 cm." },
  "english-vocabulary-01": { answer: "B", explanation: "Modern means recent or up to date, so it is the opposite of ancient." },
  "english-comprehension-01": { answer: "A", explanation: "The first drops falling suggest that it was beginning to rain." },
  "english-spelling-patterns-01": { answer: "C", explanation: "Necessary is spelled n-e-c-e-s-s-a-r-y." },
  "english-sentence-meaning-01": { answer: "B", explanation: "‘Under the weather’ is an expression that means feeling a little unwell." },
};

export function getPracticeAnswerKey(questionId: string): PracticeAnswerKey | undefined {
  return answerKeys[questionId];
}
