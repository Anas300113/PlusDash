export default function ReviewLoading() {
  return (
    <div className="page-stack review-page" aria-busy="true">
      <section className="page-intro" aria-labelledby="review-loading-title">
        <h1 id="review-loading-title" className="page-title">A quick look back</h1>
        <p>Little reviews help ideas stick.</p>
      </section>
      <div className="review-loading-state" role="status" aria-live="polite">
        <span className="review-spinner" aria-hidden="true" />
        <span>Preparing your review cards…</span>
      </div>
    </div>
  );
}
