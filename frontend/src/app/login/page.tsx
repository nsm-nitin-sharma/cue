"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck, Mail, Lock } from "lucide-react";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ tone: "sage" | "crimson"; text: string } | null>(null);

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!supabase || !isSupabaseConfigured) {
      setMessage({ tone: "crimson", text: "Supabase client is not configured." });
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      if (mode === "signup") {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setMessage({
          tone: "sage",
          text: "Account created! Check your inbox if email confirmation is enabled, or continue to plan setup.",
        });
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.push("/onboarding");
      }
    } catch (err) {
      setMessage({
        tone: "crimson",
        text: err instanceof Error ? err.message : "Authentication failed.",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    if (!supabase) return;
    setLoading(true);
    setMessage(null);
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/onboarding`,
        },
      });
      if (error) throw error;
    } catch (err) {
      setMessage({
        tone: "crimson",
        text:
          err instanceof Error
            ? `${err.message} (Enable Google provider in Supabase Auth settings when ready.)`
            : "Google OAuth not enabled yet.",
      });
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-paper paper-grain flex flex-col justify-between p-6 sm:p-10">
      <header className="max-w-5xl w-full mx-auto flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-vermilion text-white flex items-center justify-center font-semibold text-sm">
            C
          </div>
          <span className="font-semibold text-base tracking-tight text-ink">Cue</span>
        </Link>
        <Link
          href="/"
          className="text-xs font-medium text-ink-secondary hover:text-ink inline-flex items-center gap-1"
        >
          Back to Voice Desk
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </header>

      <main className="max-w-md w-full mx-auto my-8">
        <div className="bg-paper-elevated border border-rule-strong rounded-3xl shadow-dock p-7 sm:p-8">
          <div className="mb-6">
            <p className="text-[11px] font-mono uppercase tracking-wider text-vermilion">
              Store Owner Access
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-ink mt-1">
              {mode === "signin" ? "Sign in to your khata" : "Create your Cue store account"}
            </h1>
            <p className="text-xs text-ink-secondary mt-1.5 leading-relaxed">
              Protected by Supabase Auth & Row Level Security. Start free with zero card required.
            </p>
          </div>

          {/* Google OAuth Button */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-xl bg-paper border border-rule-strong hover:bg-paper-subtle text-sm font-medium text-ink flex items-center justify-center gap-2.5 transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.11-6.72-4.96H1.29v3.14C3.26 21.3 7.31 24 12 24Z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.24c-.24-.72-.38-1.49-.38-2.24s.14-1.52.38-2.24V6.62H1.29C.47 8.24 0 10.06 0 12s.47 3.76 1.29 5.38l3.99-3.14Z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.99 3.14c.95-2.85 3.6-4.96 6.72-4.96Z"
              />
            </svg>
            Continue with Google
          </button>

          <div className="my-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-rule" />
            <span className="text-[11px] font-mono text-ink-muted">OR EMAIL</span>
            <div className="h-px flex-1 bg-rule" />
          </div>

          <form onSubmit={handleEmailAuth} className="space-y-3.5">
            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">
                Email Address
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-ink-muted absolute left-3.5 top-3" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="nitin@sharmakirana.in"
                  className="w-full pl-10 pr-3.5 py-2.5 text-sm rounded-xl bg-paper border border-rule focus:outline-none focus:border-ink"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-ink-secondary mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-ink-muted absolute left-3.5 top-3" />
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-3.5 py-2.5 text-sm rounded-xl bg-paper border border-rule focus:outline-none focus:border-ink"
                />
              </div>
            </div>

            {message && (
              <div
                className={`p-3 rounded-xl text-xs border ${
                  message.tone === "sage"
                    ? "bg-sage-soft border-sage/20 text-sage"
                    : "bg-crimson-soft border-crimson/20 text-crimson"
                }`}
              >
                {message.text}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-xl bg-ink text-paper-elevated text-sm font-medium hover:bg-ink/90 transition-colors disabled:opacity-60"
            >
              {loading
                ? "Please wait..."
                : mode === "signin"
                  ? "Sign In"
                  : "Create Account"}
            </button>
          </form>

          <div className="mt-5 pt-4 border-t border-rule flex items-center justify-between text-xs">
            <button
              type="button"
              onClick={() => {
                setMode(mode === "signin" ? "signup" : "signin");
                setMessage(null);
              }}
              className="text-ink-secondary hover:text-ink underline"
            >
              {mode === "signin"
                ? "New shopkeeper? Create account"
                : "Already registered? Sign in"}
            </button>

            <Link href="/onboarding" className="text-vermilion font-medium hover:underline">
              View Plans →
            </Link>
          </div>
        </div>
      </main>

      <footer className="max-w-5xl w-full mx-auto flex items-center justify-center gap-2 text-[11px] text-ink-muted">
        <ShieldCheck className="w-3.5 h-3.5 text-sage" />
        <span>Isolated multi-tenant ledger · Row Level Security enabled</span>
      </footer>
    </div>
  );
}
