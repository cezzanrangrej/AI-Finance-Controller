import React from 'react';
import { ArrowUpRight, CheckCircle2, AlertTriangle, ArrowRight } from 'lucide-react';

export default function HumanReviewSection({ exceptions, onSelectException }) {
  if (!exceptions || exceptions.length === 0) return null;

  const humanReviewCases = exceptions.filter((e) => e.decision === 'HUMAN_REVIEW');
  const autoResolvedCases = exceptions.filter((e) => e.decision === 'AUTO_RESOLVED');

  const categoryCounts = humanReviewCases.reduce((acc, curr) => {
    acc[curr.exception_type] = (acc[curr.exception_type] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      
      {/* 1. AI INVESTIGATIONS (AUTO-RESOLVED WITH PROOF) */}
      {autoResolvedCases.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-2">
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-sm font-semibold text-slate-900">
                  AI Investigations
                </h2>
                <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  {autoResolvedCases.length} Auto-Resolved
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Evidence-backed resolutions produced by the finance investigation agent.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {autoResolvedCases.map((item) => (
              <div
                key={item.transaction_id}
                onClick={() => onSelectException(item.transaction_id)}
                className="bg-slate-50/70 border border-slate-200 hover:border-emerald-500/50 p-4 rounded-lg cursor-pointer transition-all flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-xs text-slate-900 group-hover:text-emerald-600 transition-colors">
                      {item.transaction_id}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-emerald-100/60 text-emerald-800 border border-emerald-200">
                      <CheckCircle2 className="h-3 w-3 text-emerald-600" /> AUTO-RESOLVED
                    </span>
                  </div>

                  <div className="text-[11px] font-mono text-slate-500 mt-1">
                    {item.exception_type}
                  </div>

                  <p className="text-xs text-slate-600 mt-2.5 line-clamp-3 leading-relaxed">
                    {item.reason}
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-200/80 flex items-center justify-between text-xs text-emerald-700 font-medium group-hover:text-emerald-800">
                  <span>View evidence</span>
                  <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. NEEDS HUMAN REVIEW QUEUE */}
      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-2">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-sm font-semibold text-slate-900">
                Needs Human Review
              </h2>
              <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                {humanReviewCases.length} Pending
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Exceptions where available evidence was insufficient or contradictory.
            </p>
          </div>

          {/* Compact Category Counts */}
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(categoryCounts).map(([cat, count]) => (
              <span
                key={cat}
                className="text-[10px] font-mono bg-slate-50 border border-slate-200 text-slate-600 px-2 py-0.5 rounded"
              >
                {cat.replace(/_RECORD|_ERROR/g, '').replace(/_/g, ' ')}: <strong className="text-slate-900">{count}</strong>
              </span>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {humanReviewCases.slice(0, 6).map((item) => (
            <div
              key={item.transaction_id}
              onClick={() => onSelectException(item.transaction_id)}
              className="bg-slate-50/70 border border-slate-200 hover:border-amber-500/50 p-4 rounded-lg cursor-pointer transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-xs text-slate-900 group-hover:text-amber-600 transition-colors">
                    {item.transaction_id}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-amber-100/60 text-amber-800 border border-amber-200">
                    <AlertTriangle className="h-3 w-3 text-amber-600" /> HUMAN REVIEW
                  </span>
                </div>

                <div className="text-[11px] font-mono text-slate-500 mt-1">
                  {item.exception_type}
                </div>

                <p className="text-xs text-slate-600 mt-2.5 line-clamp-3 leading-relaxed">
                  {item.reason}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-200/80 flex items-center justify-between text-xs text-amber-700 font-medium group-hover:text-amber-800">
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
