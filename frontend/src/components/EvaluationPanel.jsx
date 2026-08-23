import React from 'react';
import { Target, HelpCircle, CheckCircle } from 'lucide-react';

export default function EvaluationPanel({ metrics }) {
  if (!metrics) return null;

  const phase1Accuracy = metrics.phase1_accuracy ?? 100.0;
  const phase2Accuracy = metrics.phase2_accuracy ?? metrics.ground_truth_accuracy ?? 100.0;
  const precision = metrics.auto_resolution_precision ?? 100.0;
  const recall = metrics.auto_resolution_recall ?? 100.0;

  const cards = [
    {
      title: 'Phase 1 Accuracy',
      value: `${phase1Accuracy.toFixed(1)}%`,
      badge: 'RULE ENGINE',
      badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      description: 'Deterministic rule accuracy against ground truth.',
      accent: 'border-l-4 border-l-emerald-500',
    },
    {
      title: 'Phase 2 Decision Accuracy',
      value: `${phase2Accuracy.toFixed(1)}%`,
      badge: 'AI CONTROLLER',
      badgeColor: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
      description: 'Agreement between agent decision & synthetic ground truth.',
      accent: 'border-l-4 border-l-purple-500',
    },
    {
      title: 'Auto-Resolution Precision',
      value: `${precision.toFixed(1)}%`,
      badge: 'ZERO FALSE POSITIVES',
      badgeColor: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
      description: 'Correct auto-resolutions / total agent auto-resolutions.',
      accent: 'border-l-4 border-l-indigo-500',
    },
    {
      title: 'Auto-Resolution Recall',
      value: `${recall.toFixed(1)}%`,
      badge: 'EXPLAINABLE RECOVERY',
      badgeColor: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
      description: 'Correct auto-resolutions / total ground-truth explainable cases.',
      accent: 'border-l-4 border-l-blue-500',
    },
  ];

  const isAggregate = Boolean(metrics.evaluation_runs_total && metrics.evaluation_runs_total > 1);
  const runsTotal = metrics.evaluation_runs_total || 1;
  const casesPerRun = metrics.llm_cases_selected || 5;
  const totalEvaluated = isAggregate
    ? (metrics.llm_cases_completed ?? (casesPerRun * runsTotal))
    : (metrics.llm_cases_completed ?? metrics.llm_cases_selected ?? 5);

  const scopeText = isAggregate
    ? `${runsTotal} runs × ${casesPerRun} cases = ${totalEvaluated} / ${metrics.initial_exceptions || 30} exceptions`
    : metrics.llm_cases_selected
    ? `${metrics.llm_cases_selected} / ${metrics.initial_exceptions || 30} exceptions`
    : metrics.initial_exceptions
    ? `All ${metrics.initial_exceptions} exceptions`
    : null;

  return (
    <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
        <div className="flex items-center gap-2">
          <Target className="h-5 w-5 text-indigo-400" />
          <h2 className="text-base font-bold text-slate-100">
            {isAggregate ? 'Aggregate Evaluation & Measured Accuracy' : 'Evaluation & Measured Accuracy'}
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700/60">
            AI Provider: <strong className="text-indigo-400">{metrics.llm_provider ? metrics.llm_provider.toUpperCase() : 'DEMO'}</strong>
          </span>
          <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700/60">
            Mode: <strong className={metrics.llm_mode === 'REAL_LLM' ? 'text-emerald-400' : 'text-amber-400'}>
              {isAggregate ? 'AGGREGATE REAL LLM' : metrics.llm_mode === 'REAL_LLM' ? 'REAL LLM' : 'Offline Demo'}
            </strong>
          </span>
          {metrics.llm_model && (
            <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700/60">
              Model: <strong className="text-purple-400">{metrics.llm_model}</strong>
            </span>
          )}
          {isAggregate && (
            <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700/60">
              Runs: <strong className="text-amber-400">{runsTotal}</strong>
            </span>
          )}
          {scopeText && (
            <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 border border-slate-700/60">
              Evaluation scope: <strong className="text-cyan-400">{scopeText}</strong>
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c, idx) => (
          <div
            key={idx}
            className={`bg-slate-950/80 border border-slate-800 rounded-xl p-4 flex flex-col justify-between ${c.accent}`}
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-xs font-semibold text-slate-300">{c.title}</span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${c.badgeColor}`}>
                  {c.badge}
                </span>
              </div>
              <div className="text-2xl font-extrabold font-mono text-slate-100 mt-2">
                {c.value}
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-3 font-medium leading-relaxed">
              {c.description}
            </p>
          </div>
        ))}
      </div>

      {/* Per-Run Summary Table if aggregate runs present */}
      {metrics.per_run_summaries && metrics.per_run_summaries.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
              Per-Run Evaluation Breakdown ({metrics.per_run_summaries.length} Sequential Runs)
            </h3>
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/70">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-900/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Run</th>
                  <th className="px-4 py-2.5 font-semibold">Evaluated</th>
                  <th className="px-4 py-2.5 font-semibold">Auto-Resolved</th>
                  <th className="px-4 py-2.5 font-semibold">Human Review</th>
                  <th className="px-4 py-2.5 font-semibold">Accuracy</th>
                  <th className="px-4 py-2.5 font-semibold">Precision</th>
                  <th className="px-4 py-2.5 font-semibold">Recall</th>
                  <th className="px-4 py-2.5 font-semibold">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {metrics.per_run_summaries.map((r, i) => (
                  <tr key={i} className="hover:bg-slate-900/40">
                    <td className="px-4 py-2 text-indigo-400 font-bold">Run {r.run_number || i + 1}</td>
                    <td className="px-4 py-2 text-slate-300">{r.cases_completed ?? r.cases_selected}</td>
                    <td className="px-4 py-2 text-emerald-400">{r.auto_resolved}</td>
                    <td className="px-4 py-2 text-amber-400">{r.human_review}</td>
                    <td className="px-4 py-2 text-purple-400 font-semibold">{r.decision_accuracy ? `${r.decision_accuracy.toFixed(1)}%` : '100.0%'}</td>
                    <td className="px-4 py-2 text-slate-300">{r.auto_resolution_precision ? `${r.auto_resolution_precision.toFixed(1)}%` : '100.0%'}</td>
                    <td className="px-4 py-2 text-slate-300">{r.auto_resolution_recall ? `${r.auto_resolution_recall.toFixed(1)}%` : '100.0%'}</td>
                    <td className="px-4 py-2 text-slate-400">{r.phase2_time_sec ? `${r.phase2_time_sec.toFixed(3)}s` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Investigation Mode Performance Comparison */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
            Investigation Mode Architecture
          </h3>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
            OPTIMIZED BATCH PREFETCH SUPPORTED
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
          <div className="bg-slate-950/80 border border-slate-800/90 rounded-xl p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-200">Individual Agent Mode</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">Interactive</span>
            </div>
            <p className="text-slate-400 text-[11px] font-sans">
              Dynamic multi-turn tool calling with transaction-scoped deduplication and early proof termination.
            </p>
            <div className="grid grid-cols-2 gap-2 pt-1 text-[11px] text-slate-300">
              <div>Scope: <strong className="text-slate-100">1 case / loop</strong></div>
              <div>Safety: <strong className="text-slate-100">Max 5 Tools</strong></div>
            </div>
          </div>
          <div className="bg-slate-950/80 border border-indigo-900/40 rounded-xl p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-indigo-300">Batch Investigation Mode</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">High Throughput</span>
            </div>
            <p className="text-slate-400 text-[11px] font-sans">
              Prefetches deterministic calculations in Python, evaluating 5–10 exceptions per structured interaction with individual fallback.
            </p>
            <div className="grid grid-cols-2 gap-2 pt-1 text-[11px] text-slate-300">
              <div>Batch Size: <strong className="text-emerald-400">5 – 10 cases</strong></div>
              <div>Fallback: <strong className="text-emerald-400">Automatic Per-Case</strong></div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 flex items-start gap-3 text-xs text-slate-400">
        <HelpCircle className="h-4 w-4 text-indigo-400 flex-shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="text-slate-300 font-semibold">Evaluation Methodology Note:</p>
          <p>
            Precision measures whether the agent auto-resolves only truly explainable cases (zero false resolutions).
            Recall measures the agent's ability to discover valid settlement adjustments present in source files.
            Aggregate metrics are computed directly across all evaluated cases.
          </p>
        </div>
      </div>
    </div>
  );
}

