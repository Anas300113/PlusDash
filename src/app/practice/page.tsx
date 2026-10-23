import { Suspense } from "react";
import { PracticeSession } from "@/components/practice-session";

export default function PracticePage() {
  return (
    <Suspense fallback={<main className="practice-frame"><p className="practice-loading">Getting your question ready…</p></main>}>
      <PracticeSession />
    </Suspense>
  );
}
