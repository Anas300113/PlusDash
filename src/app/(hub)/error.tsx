"use client";

export default function HubError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section className="error-state-card" role="alert" aria-labelledby="hub-error-title">
      <h1 id="hub-error-title" className="page-title">That didn’t go to plan.</h1>
      <p>Something didn’t load as expected. Try again when you’re ready.</p>
      <button className="button button-primary" onClick={reset}>Try again</button>
    </section>
  );
}
