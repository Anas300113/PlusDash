# Plus11 Interface Design System

## Authority

The user-provided `Plus11+AppDesign.pdf` is the source of truth for visual identity and the core Today, Learn, and Practice screen composition; its source file is supplied separately and is not packaged with the application. Do not replace it with generic education-app conventions. The approved work is an Operate surface: prioritize legibility, predictable task completion, and restrained polish.

## Design movement and principles

A crisp, paper-and-ink learning companion with small hand-drawn warmth. Keep the interface calm and confident; use whitespace and clear outlines to organize content; reserve the yellow highlighter for meaningful progress, wins, current selection, and short emphasis; maintain a supportive voice without infantilizing or shaming the learner.

## Color tokens

- Ink: `#141414` — primary text, outline, and primary action.
- Paper: `#FBFAF6` — app canvas.
- Highlighter: `#FFD84D` — restrained progress and active/win accent only.
- Page: `#FFFFFF` — card and question surfaces.
- Pencil: `#5A5A55` — secondary text, subject to contrast checks.
- Muted line: `#D8D7D1` — inactive tracker and quiet separators.

Do not add a competing accent palette, gradients, dark mode, glass, or decorative textures. Check all text combinations and darken secondary text where required for contrast.

## Typography

Patrick Hand for headings and short expressive labels. Nunito for questions, answers, instructions, controls, metadata, and other close-reading content. No text below 12px; body and question text should ordinarily be 16px or above. Keep line lengths and wraps comfortable.

## Composition and components

Use generous but purposeful whitespace, a warm-paper canvas, white paper cards, crisp ink outlines (typically 1.5–2px), modest 12–16px card corners, and little or no shadow. Avoid nested-card layouts and generic icon-plus-heading card grids as the sole composition. Keep a clear readable content measure and a stable mobile app shell. Use consistent SVG icons around 2px stroke with rounded ends/corners; no emoji. The Plus mark is an owl perched on an open book, kept small and unobtrusive.

The learner hub uses the four destinations Today, Learn, Progress, and Review. Practice is a focused subflow with its own progress/timer header, answer choices, and bottom actions. Progress trackers must include textual/accessibility equivalents; no state is communicated by color alone.

## Interaction and motion

Controls clearly show hover, pressed, selected, disabled, and focus states. The whole visible row/card may be actionable only when its behavior is clear. Use Framer Motion for a few short, meaningful state/screen transitions (roughly 150–300ms), animate progress only when it communicates an actual update, and keep actions interruptible. Respect `prefers-reduced-motion`; no continuous, distracting, or celebratory motion overload.

## Brand voice

Short, plain-language, warm, and respectful. Examples from the reference: “Hi Sam, ready for a quick one?” and “Pick up where it’s wobbly.” Keep helpful explanations specific and make errors actionable. Do not use pressure or punitive language.
