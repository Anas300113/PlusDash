"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, CircleUserRound, LoaderCircle, LogIn, LogOut, Save, ShieldCheck } from "lucide-react";
import { useSession, startSignIn } from "@/components/session-provider";
import { apiWrite } from "@/lib/client-api";

type AccountScreenProps = { authResult?: string };

export function AccountScreen({ authResult }: AccountScreenProps) {
  const { status, user, csrfToken, error, refresh } = useSession();
  const [draft, setDraft] = useState<{ key: string; value: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(authResult === "success" ? "You’re signed in. Your learning will be saved to your account." : null);
  const [formError, setFormError] = useState<string | null>(authResult === "error" ? "Sign-in didn’t finish. Please try again." : null);

  const displayName = user ? draft?.key === csrfToken ? draft.value : user.displayName : "";

  if (status === "loading") {
    return (
      <div className="page-stack account-page" aria-live="polite">
        <section className="page-intro"><h1 className="page-title">Your account</h1><p>Getting your Plus11 space ready…</p></section>
        <div className="account-state-card"><LoaderCircle className="account-spinner" size={22} aria-hidden="true" /><span>Checking your account</span></div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="page-stack account-page">
        <section className="page-intro"><h1 className="page-title">Your account</h1><p>We couldn’t check your account just now.</p></section>
        <section className="account-state-card" role="alert"><p>{error ?? "Please try again when your connection is ready."}</p><button className="button button-secondary" onClick={() => void refresh()}>Try again</button></section>
      </div>
    );
  }

  if (status === "guest" || !user) {
    return (
      <div className="page-stack account-page">
        <section className="page-intro"><h1 className="page-title">Your account</h1><p>Keep your own learning and progress together.</p></section>
        <section className="account-card account-guest">
          <span className="account-mark"><CircleUserRound size={25} strokeWidth={1.8} aria-hidden="true" /></span>
          <div className="account-copy"><h2>You’re exploring as a guest</h2><p>The progress around Plus11 is sample content. Sign in to save your real practice, topic progress, and review cards to your account.</p></div>
          <button className="button button-primary account-signin" onClick={startSignIn}><LogIn size={17} aria-hidden="true" /> Sign in with Manus <ArrowRight size={16} aria-hidden="true" /></button>
          <p className="account-privacy"><ShieldCheck size={17} aria-hidden="true" /> We use your Manus account for sign-in. Plus11 saves only your learner name and learning activity.</p>
          {formError ? <p className="account-message account-message-error" role="alert">{formError}</p> : null}
        </section>
      </div>
    );
  }

  async function saveName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!csrfToken) return;
    setSaving(true);
    setFeedback(null);
    setFormError(null);
    try {
      const result = await apiWrite<{ user: { displayName: string } }>("/api/account", csrfToken, "PATCH", { displayName });
      setDraft({ key: csrfToken, value: result.user.displayName });
      await refresh();
      setFeedback("Your name has been saved.");
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "We couldn’t save your name just now.");
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    if (!csrfToken) return;
    setSigningOut(true);
    setFeedback(null);
    setFormError(null);
    try {
      await apiWrite<{ signedOut: boolean }>("/api/auth/logout", csrfToken, "POST");
      await refresh();
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "We couldn’t sign you out just now.");
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="page-stack account-page">
      <section className="page-intro"><h1 className="page-title">Your account</h1><p>Your learning stays with you when you sign in.</p></section>
      <section className="account-card account-signed-in" aria-labelledby="account-profile-heading">
        <div className="account-profile-heading">
          <span className="account-mark"><CircleUserRound size={25} strokeWidth={1.8} aria-hidden="true" /></span>
          <div><h2 id="account-profile-heading">Signed in with Manus</h2><p>Your practice and progress are saved privately to this account.</p></div>
        </div>
        <form className="account-form" onSubmit={saveName}>
          <label htmlFor="learner-display-name">What should we call you?</label>
          <div className="account-input-row">
            <input id="learner-display-name" name="displayName" type="text" autoComplete="nickname" minLength={2} maxLength={40} required value={displayName} onChange={(event) => csrfToken && setDraft({ key: csrfToken, value: event.target.value })} />
            <button className="button button-primary" type="submit" disabled={saving || displayName.trim() === user.displayName.trim()}><Save size={16} aria-hidden="true" /> {saving ? "Saving…" : "Save name"}</button>
          </div>
          <p className="account-helper">Use 2–40 characters. Your name is shown only in your Plus11 space.</p>
          {feedback ? <p className="account-message" role="status">{feedback}</p> : null}
          {formError ? <p className="account-message account-message-error" role="alert">{formError}</p> : null}
        </form>
        <div className="account-security-note"><ShieldCheck size={18} aria-hidden="true" /><p>Only your own learning activity is connected to this account. We don’t ask for your school or date of birth.</p></div>
        <button className="button button-secondary account-signout" type="button" onClick={() => void signOut()} disabled={signingOut}><LogOut size={17} aria-hidden="true" /> {signingOut ? "Signing out…" : "Sign out"}</button>
      </section>
    </div>
  );
}
