# Plus11 Frontend ToDo

## Today dashboard
- [x] Build the Today dashboard with Plus owl/wordmark, a 12-day streak, “Hi Sam, ready for a quick one?”, an 18-of-30-minute progress ring, “Nearly there. 12 minutes to go.”, and a working “Continue practice” action.
- [x] Show Today’s plan with “1 of 3 done” and all three activities: Maths: fractions — 10 questions, done; Verbal reasoning: odd one out — 8 questions, 5 to go; Review: 6 cards due — about 4 minutes.
- [x] Include a Mon–Sun streak strip and Today/Learn/Progress/Review primary navigation; completed, active, and future states must be understandable without color alone.

## Learn and subject/topic selection
- [x] Show “What shall we learn? Pick a subject, then a topic.” with interactive subject cards: Maths 72% mastered/14 topics; English 58%/12; Verbal reasoning 44%/10; Non-verbal reasoning 31%/9.
- [x] Show “Pick up where it’s wobbly”: Non-verbal: rotations, 3 of the last 5 answers missed, with a working Try action.
- [x] Show “Timed mock paper” as locked with “Unlocks after 5 more topics”; it must not masquerade as an available action.
- [x] Subject selection opens topic choices; topic actions start or continue the related practice, and each of the 16 sample topics routes to a matching subject/topic question set.

## Focused practice flow
- [x] Build the verbal-reasoning question flow with a predictable close/exit action, 5-of-8 progress, timer 0:42, “Verbal reasoning, odd one out,” prompt “Which word is the odd one out?”, and support “Think about what the others have in common.”
- [x] Provide keyboard-operable, touch-friendly options A Violin, B Trumpet, C Cello, D Harp. Selecting an option and submitting it are distinct actions; the selected choice is visibly indicated.
- [x] Provide an actionable Hint, a Check answer action, and Continue after feedback. The correct answer is B — Trumpet. After checking, show a constructive accessible explanation, update session progress, and allow the next question.
- [x] Hints offer a useful clue without immediately giving away the answer. Answer feedback and focus handling must work for keyboard and assistive technology users.

## Progress and Review
- [x] Progress shows accessible overall and per-subject mastery/activity summaries based on the sample figures, plus an actionable next-step recommendation.
- [x] Review shows 6 due cards and an approximately four-minute estimate, an interactive review-start flow with progress handling, and sensible loading and empty states.

## Navigation and client-side state
- [x] Use coherent App Router navigation for Today, Learn, Progress, Review, subject/topic choices, and practice. Routes must support deep linking and browser-back-friendly behavior.
- [x] Navigation, subject/topic selection, practice, hint, answer check/feedback, continue, review start, and relevant list actions work using client-side sample data/state only.
- [x] Provide meaningful selected, disabled, loading, empty, error, and completion states wherever applicable. Do not ship dead-looking or dead-end controls.

## Visual design system
- [x] Follow the PDF-authoritative paper-and-ink identity: Ink `#141414`, Paper `#FBFAF6`, Highlighter `#FFD84D` only for progress/wins/current emphasis, Page `#FFFFFF`, Pencil `#5A5A55`; contrast-check all combinations.
- [x] Use Patrick Hand headings and Nunito questions, answers, and close-reading text; never render text below 12px.
- [x] Use simple 2px rounded-stroke SVG icons and a Plus owl-on-open-book mark; no emoji icons.
- [x] Preserve generous whitespace, crisp outlines, restrained modest corners, and white cards. No gradients, glassmorphism, dark mode, extra color palette, or childish decoration.
- [x] Keep reusable components and design tokens consistent across all screens.

## Responsive, motion, and accessibility
- [x] Optimize mobile-first layouts around 375, 768, 1024, and 1440px; no horizontal overflow, clipped text, or obscured actions.
- [x] Use Framer Motion for subtle, meaningful 150–300ms transitions; support reduced motion and keep interactions interruptible.
- [x] Use semantic markup, visible keyboard focus, logical tab order, labels, accessible navigation state, and accessible answer/progress announcements.
- [x] Maintain body text contrast of at least 4.5:1; no state conveyed by color alone; no hover-only behavior; touch targets at least 44×44px.
- [x] Keep layout stable during loading and use respectful, non-punitive learner-facing copy.

## Engineering and handoff
- [x] Use the latest stable Next.js App Router, React, and TypeScript; use Framer Motion; keep the deliverable frontend-only with no backend, database, login, or outside integration.
- [x] Use a maintainable component/data structure, avoid unnecessary dependencies and layout shifts, and provide app metadata/title.
- [x] Run available lint, TypeScript, and production build checks and correct applicable failures.
- [x] Inspect the rendered interface at mobile and desktop sizes and fix visible clipping, awkward wrapping, inconsistent spacing, and unclear states before handoff.
