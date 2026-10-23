import {
  BookOpenText,
  Calculator,
  MessageSquareText,
  Shapes,
  type LucideIcon,
} from "lucide-react";

export type SubjectId = "maths" | "english" | "verbal-reasoning" | "non-verbal-reasoning";

export type Subject = {
  id: SubjectId;
  name: string;
  mastery: number;
  topicCount: number;
  icon: LucideIcon;
  topics: string[];
};

export const subjects: Subject[] = [
  {
    id: "maths",
    name: "Maths",
    mastery: 72,
    topicCount: 14,
    icon: Calculator,
    topics: ["Fractions", "Number sequences", "Ratio and proportion", "Area and perimeter"],
  },
  {
    id: "english",
    name: "English",
    mastery: 58,
    topicCount: 12,
    icon: BookOpenText,
    topics: ["Comprehension", "Vocabulary", "Spelling patterns", "Sentence meaning"],
  },
  {
    id: "verbal-reasoning",
    name: "Verbal reasoning",
    mastery: 44,
    topicCount: 10,
    icon: MessageSquareText,
    topics: ["Odd one out", "Word links", "Letter sequences", "Code words"],
  },
  {
    id: "non-verbal-reasoning",
    name: "Non-verbal reasoning",
    mastery: 31,
    topicCount: 9,
    icon: Shapes,
    topics: ["Rotations", "Shape sequences", "Reflections", "Missing shapes"],
  },
];

export const weekDays = [
  { label: "Mon", state: "complete" },
  { label: "Tue", state: "complete" },
  { label: "Wed", state: "complete" },
  { label: "Thu", state: "complete" },
  { label: "Fri", state: "today" },
  { label: "Sat", state: "upcoming" },
  { label: "Sun", state: "upcoming" },
] as const;

export const reviewCards = [
  {
    topic: "Fractions",
    prompt: "How can you simplify 6/8?",
    answer: "Divide the top and bottom by 2: 6/8 simplifies to 3/4.",
  },
  {
    topic: "Rotations",
    prompt: "What happens to a shape after a quarter turn?",
    answer: "It turns through 90 degrees around a fixed point.",
  },
  {
    topic: "Word links",
    prompt: "Which word means the opposite of ‘generous’?",
    answer: "‘Selfish’ is an opposite of generous.",
  },
  {
    topic: "Number sequences",
    prompt: "What is the next number: 4, 8, 12, …?",
    answer: "16. Each step adds 4.",
  },
  {
    topic: "Comprehension",
    prompt: "What does a character’s action tell you?",
    answer: "It can give a clue about what the character thinks or feels.",
  },
  {
    topic: "Shape sequences",
    prompt: "What should you check first in a shape pattern?",
    answer: "Look for what changes each step: shape, position, size, or direction.",
  },
];
