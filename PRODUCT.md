# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

User-selected: latest stable Next.js App Router, React, TypeScript, and Framer Motion.

## Users

The primary users are school-age learners preparing for 11-plus-style assessments. The exact age range and parent/teacher roles are not specified. The interface should speak directly to the learner in clear, encouraging language.

## Product Purpose

Plus11 supports short, structured learning and practice across Maths, English, Verbal Reasoning, and Non-verbal Reasoning. Learners can follow a daily plan, continue practice, pick a subject and topic, review weaker topics and due cards, manage their account, and see progress. Success means it is obvious what to do next and the learner can complete a practice or review session with confidence; signed-in learning progress remains theirs when they return.

## Positioning

The approved frontend concept combines a clear daily study plan, focused question practice, mastery by subject, weak-topic prompts, streaks, and spaced review in one calm 11-plus learning companion. This describes the requested interface; no market-exclusivity claim is established.

## Operating Context

The app is designed for learners to use on mobile and desktop for short practice sessions. Key workflows include opening Today, continuing the next planned activity, choosing a subject/topic, answering a question, using a hint, checking an answer, continuing a session, reviewing due cards, and navigating among Today, Learn, Progress, and Review.

The original frontend-only scope has been extended by the user's follow-up request to add an account area and make learning data work with a backend. The intended default identity provider is Manus OAuth because no alternative was requested. A single learner's profile and learning activity should be isolated and saved across sessions; the static question/topic catalogue remains product content. Logged-out learners may browse demo/sample figures, but those figures must never be presented as the signed-in learner's real history.

## Capabilities and Constraints

- Implement the complete interactive frontend for Today, Learn, Progress, Review, subject/topic selection, and focused practice.
- Support client-side example state for the anonymous/demo flow and server-backed, per-account state for signed-in learners.
- Provide an account section with accurate signed-in/out, loading, error, profile, and sign-out states.
- Default to Manus OAuth; do not build a separate password store or add another identity provider unless the user asks.
- Persist real practice attempts, topic mastery, daily activity, plan completions, and review-card scheduling under the authenticated learner only.
- Keep authenticated progress truthful: a new account starts without invented streaks, completed tasks, mastery, or due cards.
- Minimize personal data: do not add date of birth, school, parent contact, or other profile fields not requested. Do not persist OAuth email unless a later feature needs it and the user approves.
- Preserve predictable URLs and browser-back behavior.
- The timed mock paper is shown as locked until five more topics are completed.
- Do not invent unrelated features, external integrations, customer claims, or performance evidence.
- Managed server and database activation is one-way and must wait for the user's explicit confirmation; development and publication share the managed database.

## Brand Commitments

The product name is Plus11. The user-provided `Plus11+AppDesign.pdf` is the binding visual reference. Its identity is ink and warm paper, generous white space, and restrained highlighter-yellow progress/win emphasis. Preserve the exact palette, Patrick Hand headings, Nunito close-reading text, simple 2px rounded-stroke icons, and owl on an open book motif described in the PDF. The voice is concise, supportive, clear, and never shaming.

## Evidence on Hand

- Supplied visual/product reference: `/home/ubuntu/upload/Plus11+AppDesign.pdf` (four pages).
- The PDF contains sample Today, Learn, and question screens and the palette/type/icon/tracker rules.
- Approved blueprint supplies Progress and Review screen scope.
- User follow-up (2026-10-24): “Can you add an accounts section and make sure everything with smoothly intergrate with the backend and will work”.
- No validated product analytics, customer testimonials, real learner records, or performance claims were supplied. Use sample values as illustrative UI content only.

## Product Principles

1. Make the learner’s next useful action obvious.
2. Turn progress and mistakes into supportive guidance, never judgement.
3. Keep the practice flow focused, legible, and predictable.
4. Reuse the same product language and interaction patterns across screens.
5. Keep account identity and learning data minimal, private, and scoped to the signed-in learner.

## Accessibility & Inclusion

The frontend must be mobile-first and keyboard operable, use semantic HTML and visible focus, maintain at least 4.5:1 body-text contrast, use touch targets of at least 44×44px, avoid hover-only interactions and color-only status cues, provide accessible answer feedback, and respect reduced-motion preferences. Keep text at least 12px, with comfortable close-reading sizes.
