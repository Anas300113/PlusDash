# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

User-selected: latest stable Next.js App Router, React, TypeScript, and Framer Motion.

## Users

The primary users are school-age learners preparing for 11-plus-style assessments. The exact age range and parent/teacher roles are not specified. The interface should speak directly to the learner in clear, encouraging language.

## Product Purpose

Plus11 supports short, structured learning and practice across Maths, English, Verbal Reasoning, and Non-verbal Reasoning. Learners can follow a daily plan, continue practice, pick a subject and topic, review weaker topics and due cards, and see progress. Success means it is obvious what to do next and the learner can complete a practice or review session with confidence.

## Positioning

The approved frontend concept combines a clear daily study plan, focused question practice, mastery by subject, weak-topic prompts, streaks, and spaced review in one calm 11-plus learning companion. This describes the requested interface; no market-exclusivity claim is established.

## Operating Context

The app is designed for learners to use on mobile and desktop for short practice sessions. Key workflows include opening Today, continuing the next planned activity, choosing a subject/topic, answering a question, using a hint, checking an answer, continuing a session, reviewing due cards, and navigating among Today, Learn, Progress, and Review. Frontend-only sample data and client-side state are in scope; no account, server, or persistent database is requested.

## Capabilities and Constraints

- Implement the complete interactive frontend for Today, Learn, Progress, Review, subject/topic selection, and focused practice.
- Support client-side example state for plan completion, answer choice, hint, answer feedback, session progress, and review flow.
- Preserve predictable URLs and browser back behavior.
- Do not invent unrelated features, external integrations, customer claims, performance evidence, or persistent backend behavior.
- The timed mock paper is shown as locked until five more topics are completed.
- Brand question example: “Which word is the odd one out?” with Violin, Trumpet, Cello, and Harp; B — Trumpet is the correct answer.

## Brand Commitments

The product name is Plus11. The user-provided `Plus11+AppDesign.pdf` is the binding visual reference. Its identity is ink and warm paper, generous white space, and restrained highlighter-yellow progress/win emphasis. Preserve the exact palette, Patrick Hand headings, Nunito close-reading text, simple 2px rounded-stroke icons, and owl on an open book motif described in the PDF. The voice is concise, supportive, clear, and never shaming.

## Evidence on Hand

- Supplied visual/product reference: `/home/ubuntu/upload/Plus11+AppDesign.pdf` (four pages).
- The PDF contains sample Today, Learn, and question screens and the palette/type/icon/tracker rules.
- Approved blueprint supplies Progress and Review screen scope.
- No validated product analytics, customer testimonials, real learner records, or performance claims were supplied. Use sample values as illustrative UI content only.

## Product Principles

1. Make the learner’s next useful action obvious.
2. Turn progress and mistakes into supportive guidance, never judgement.
3. Keep the practice flow focused, legible, and predictable.
4. Reuse the same product language and interaction patterns across screens.

## Accessibility & Inclusion

The frontend must be mobile-first and keyboard operable, use semantic HTML and visible focus, maintain at least 4.5:1 body-text contrast, use touch targets of at least 44×44px, avoid hover-only interactions and color-only status cues, provide accessible answer feedback, and respect reduced-motion preferences. Keep text at least 12px, with comfortable close-reading sizes.