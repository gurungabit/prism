import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useStartAnalysis, useHistory } from "../hooks/useAnalysis";
import { Input, Textarea } from "../components/shared/Input";
import { Button } from "../components/shared/Button";
import type { AnalysisInput } from "../lib/api";
import {
  FlaskConical,
  ChevronRight,
  Triangle,
  Plus,
  ArrowRight,
  Clock,
} from "lucide-react";

const SUGGESTIONS = [
  "Add real-time notifications to the mobile app",
  "Migrate authentication to OAuth 2.0",
  "Implement data export for compliance reporting",
  "Build a self-service admin dashboard",
];

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const seconds = Math.floor((now - then) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

export function AnalyzePage() {
  const [analysisInput, setAnalysisInput] = useState<AnalysisInput>({
    requirement: "",
    business_goal: "",
    context: "",
    constraints: "",
    known_teams: "",
    known_services: "",
    questions_to_answer: "",
  });
  const [showContext, setShowContext] = useState(false);
  const navigate = useNavigate();
  const startAnalysis = useStartAnalysis();
  const history = useHistory(3, 0);

  function updateField<K extends keyof AnalysisInput>(key: K, value: string) {
    setAnalysisInput((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!analysisInput.requirement?.trim()) return;

    const result = await startAnalysis.mutateAsync({
      ...analysisInput,
      requirement: analysisInput.requirement.trim(),
      business_goal: analysisInput.business_goal?.trim() || "",
      context: analysisInput.context?.trim() || "",
      constraints: analysisInput.constraints?.trim() || "",
      known_teams: analysisInput.known_teams?.trim() || "",
      known_services: analysisInput.known_services?.trim() || "",
      questions_to_answer: analysisInput.questions_to_answer?.trim() || "",
    });
    navigate({ to: "/analyze/$runId", params: { runId: result.analysis_id } });
  }

  return (
    <div className="relative min-h-full flex items-center justify-center px-6 py-16 overflow-hidden">
      <div
        className="analyze-glow pointer-events-none absolute inset-0 flex items-center justify-center"
        aria-hidden="true"
      >
        <div className="w-[600px] h-[600px] rounded-full bg-[radial-gradient(circle,_var(--color-accent-muted)_0%,_transparent_70%)] dark:bg-[radial-gradient(circle,_var(--color-accent-dark-muted)_0%,_transparent_70%)] blur-3xl opacity-80" />
      </div>

      <div className="relative w-full max-w-[680px] stagger-children">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center mb-5">
            <div className="relative">
              <div className="absolute inset-0 rounded-full bg-[var(--color-accent-subtle)] dark:bg-[var(--color-accent-dark-subtle)] blur-xl scale-[2.5]" />
              <div className="relative w-10 h-10 rounded-xl bg-[var(--color-accent-muted)] dark:bg-[var(--color-accent-dark-muted)] border border-[var(--color-accent-subtle)] dark:border-[var(--color-accent-dark-subtle)] flex items-center justify-center">
                <Triangle className="w-4 h-4 text-[var(--color-accent)] dark:text-[var(--color-accent-dark)]" />
              </div>
            </div>
          </div>

          <h1 className="text-2xl tracking-tight text-zinc-900 dark:text-zinc-100">
            What should we analyze?
          </h1>
          <p className="text-[13px] text-zinc-400 dark:text-zinc-500 mt-2.5 max-w-[440px] mx-auto leading-relaxed">
            Describe the requirement and the planning context around it.
            PRISM will turn that into ownership, service impact, risks,
            effort, and evidence quality.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Textarea
              label="Requirement"
              placeholder="e.g., Add real-time notifications to the mobile app..."
              value={analysisInput.requirement}
              onChange={(e) => updateField("requirement", e.target.value)}
              className="min-h-[140px] analyze-textarea"
              required
            />
          </div>

          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => updateField("requirement", s)}
                className="inline-flex items-center text-[11px] px-2.5 py-1 rounded-full border border-zinc-200/80 dark:border-zinc-700/50 text-zinc-400 dark:text-zinc-500 hover:text-[var(--color-accent)] dark:hover:text-[var(--color-accent-dark)] hover:border-[var(--color-accent-subtle)] dark:hover:border-[var(--color-accent-dark-subtle)] transition-colors duration-150 bg-white/50 dark:bg-zinc-800/30"
              >
                {s}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Textarea
              label="Business Goal"
              placeholder="Why does this matter now? Revenue, customer pain, compliance, launch milestone..."
              value={analysisInput.business_goal}
              onChange={(e) => updateField("business_goal", e.target.value)}
              className="min-h-[96px]"
            />
            <Textarea
              label="Constraints"
              placeholder="Deadlines, systems we cannot break, staffing limits, rollout constraints..."
              value={analysisInput.constraints}
              onChange={(e) => updateField("constraints", e.target.value)}
              className="min-h-[96px]"
            />
          </div>

          <div>
            {!showContext ? (
              <button
                type="button"
                onClick={() => setShowContext(true)}
                className="inline-flex items-center gap-1.5 text-[11px] font-medium text-zinc-400 dark:text-zinc-500 hover:text-[var(--color-accent)] dark:hover:text-[var(--color-accent-dark)] transition-colors duration-150"
              >
                <Plus className="w-3 h-3" />
                Add context
              </button>
            ) : (
              <div className="animate-slide-up">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Textarea
                    label="Additional Context"
                    placeholder="Background, linked initiatives, architecture notes, customer details..."
                    value={analysisInput.context}
                    onChange={(e) => updateField("context", e.target.value)}
                    className="min-h-[96px]"
                  />
                  <Textarea
                    label="Questions To Answer"
                    placeholder="Which team should own it? What services are impacted? What are the blockers?"
                    value={analysisInput.questions_to_answer}
                    onChange={(e) => updateField("questions_to_answer", e.target.value)}
                    className="min-h-[96px]"
                  />
                  <Input
                    label="Known Teams"
                    placeholder="platform-team, payments-team, security-team"
                    value={analysisInput.known_teams}
                    onChange={(e) => updateField("known_teams", e.target.value)}
                  />
                  <Input
                    label="Known Services"
                    placeholder="auth-service, api-gateway, invoice-service"
                    value={analysisInput.known_services}
                    onChange={(e) => updateField("known_services", e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-end pt-1">
            <Button
              type="submit"
              loading={startAnalysis.isPending}
              icon={<FlaskConical className="w-3.5 h-3.5" />}
              size="lg"
            >
              Run Analysis
            </Button>
          </div>
        </form>

        {history.data && history.data.threads.length > 0 && (
          <div className="mt-12 pt-6 border-t border-zinc-100 dark:border-zinc-700/40">
            <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              Recent
            </span>
            <div className="mt-3 space-y-0.5">
              {history.data.threads.map((thread) => (
                <Link
                  key={thread.thread_id}
                  to="/analyze/$runId"
                  params={{ runId: thread.thread_id }}
                  className="flex items-center justify-between px-3 py-2.5 -mx-3 rounded-lg hover:bg-zinc-50 dark:hover:bg-zinc-700/30 transition-colors duration-150 group analyze-history-item"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-[12px] text-zinc-500 dark:text-zinc-400 truncate group-hover:text-[var(--color-accent)] dark:group-hover:text-[var(--color-accent-dark)] transition-colors duration-150">
                      {thread.requirement}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                    <span className="flex items-center gap-1 text-[10px] text-zinc-300 dark:text-zinc-600">
                      <Clock className="w-2.5 h-2.5" />
                      {timeAgo(thread.last_turn_at)}
                    </span>
                    <ChevronRight className="w-3 h-3 text-zinc-300 dark:text-zinc-700 group-hover:text-[var(--color-accent)] dark:group-hover:text-[var(--color-accent-dark)] transition-colors duration-150" />
                  </div>
                </Link>
              ))}
            </div>

            <Link
              to="/history"
              className="inline-flex items-center gap-1 mt-3 text-[11px] font-medium text-zinc-400 dark:text-zinc-500 hover:text-[var(--color-accent)] dark:hover:text-[var(--color-accent-dark)] transition-colors duration-150"
            >
              View all
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
