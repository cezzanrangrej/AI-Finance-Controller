import React from 'react';
import { ArrowUpRight, CheckCircle2, AlertTriangle, ArrowRight } from 'lucide-react';

export default function HumanReviewSection({ exceptions, onSelectException }) {
  if (!exceptions || exceptions.length === 0) return null;

  const humanReviewCases = exceptions.filter((e) => e.decision === 'HUMAN_REVIEW' || e.decision === 'NOT_EVALUATED');
  const autoResolvedCases = exceptions.filter((e) => e.decision === 'AUTO_RESOLVED');

  const categoryCounts = humanReviewCases.reduce((acc, curr) => {
    acc[curr.exception_type] = (acc[curr.exception_type] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      
      {/* 1. AI INVESTIGATIONS (AUTO-RESOLVED WITH PROOF) */}
      {autoResolvedCases.length > 0 && (
        <div className="bg-background border border-border rounded-lg p-6 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-border gap-2">
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-sm font-semibold text-text">
                  AI Investigations
                </h2>
                <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-accent-green/10 text-text border border-accent-green/30">
                  {autoResolvedCases.length} Auto-Resolved
                </span>
              </div>
              <p className="text-xs text-text-secondary mt-0.5">
                Evidence-backed resolutions produced by the finance investigation agent.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {autoResolvedCases.map((item) => (
              <div
                key={item.transaction_id}
                onClick={() => onSelectException(item.transaction_id)}
                className="bg-surface border border-border hover:border-accent-green/50 p-4 rounded-lg cursor-pointer transition-all flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-xs text-text group-hover:text-primary transition-colors">
                      {item.transaction_id}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-accent-green/10 text-text border border-accent-green/30">
                      <CheckCircle2 className="h-3 w-3 text-text" /> AUTO-RESOLVED
                    </span>
                  </div>

                  <div className="text-[11px] font-mono text-text-secondary mt-1">
                    {item.exception_type}
                  </div>

                  <p className="text-xs text-text-secondary mt-2.5 line-clamp-3 leading-relaxed">
                    {item.reason}
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-xs text-text font-medium group-hover:text-primary">
                  <span>View evidence</span>
                  <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. NEEDS HUMAN REVIEW QUEUE */}
      <div className="bg-background border border-border rounded-lg p-6 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-border gap-2">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-sm font-semibold text-text">
                Needs Human Review
              </h2>
              <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-accent-coral/10 text-text border border-accent-coral/30">
                {humanReviewCases.length} Pending
              </span>
            </div>
            <p className="text-xs text-text-secondary mt-0.5">
              Exceptions where available evidence was insufficient or contradictory.
            </p>
          </div>

          {/* Compact Category Counts */}
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(categoryCounts).map(([cat, count]) => (
              <span
                key={cat}
                className="text-[10px] font-mono bg-surface border border-border text-text-secondary px-2 py-0.5 rounded"
              >
                {cat.replace(/_RECORD|_ERROR/g, '').replace(/_/g, ' ')}: <strong className="text-text">{count}</strong>
              </span>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {humanReviewCases.slice(0, 6).map((item) => (
            <div
              key={item.transaction_id}
              onClick={() => onSelectException(item.transaction_id)}
              className="bg-surface border border-border hover:border-accent-coral/50 p-4 rounded-lg cursor-pointer transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-xs text-text group-hover:text-accent-coral transition-colors">
                    {item.transaction_id}
                  </span>
                  {item.decision === 'NOT_EVALUATED' ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30">
                      <AlertTriangle className="h-3 w-3 text-amber-500" /> PROVIDER OUTAGE — not yet evaluated
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-accent-coral/10 text-text border border-accent-coral/30">
                      <AlertTriangle className="h-3 w-3 text-accent-coral" /> HUMAN REVIEW
                    </span>
                  )}
                </div>

                <div className="text-[11px] font-mono text-text-secondary mt-1">
                  {item.exception_type}
                </div>

                <p className="text-xs text-text-secondary mt-2 line-clamp-2 leading-relaxed">
                  {item.reason}
                </p>

                {item.recommended_action && (
                  <div className="mt-2 text-[11px] font-sans text-text bg-accent-coral/10 border border-accent-coral/30 px-2 py-1 rounded">
                    <span className="font-semibold text-text">Action:</span> {item.recommended_action}
                  </div>
                )}
              </div>

              <div className="mt-3 pt-2.5 border-t border-border flex items-center justify-between text-xs text-text font-medium group-hover:text-accent-coral">
                <span>Review case</span>
                <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
