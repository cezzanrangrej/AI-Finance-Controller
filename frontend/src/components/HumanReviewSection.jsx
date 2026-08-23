import React from 'react';
import { AlertCircle, ArrowRight, ShieldAlert, CheckCircle2, Bot } from 'lucide-react';

export default function HumanReviewSection({ exceptions, onSelectException }) {
  if (!exceptions) return null;

  const humanReviewCases = exceptions.filter((e) => e.decision === 'HUMAN_REVIEW');
  const autoResolvedCases = exceptions.filter((e) => e.decision === 'AUTO_RESOLVED');

  const categoryCounts = humanReviewCases.reduce((acc, curr) => {
    acc[curr.exception_type] = (acc[curr.exception_type] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      
      {/* 1. HOW THE AGENT CLOSED THE LOOP */}
      {autoResolvedCases.length > 0 && (
        <div className="bg-indigo-950/20 border border-indigo-500/30 rounded-2xl p-6 shadow-md backdrop-blur-md">
          <div className="flex items-center justify-between pb-4 border-b border-indigo-500/20 mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                <Bot className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-base font-bold text-indigo-200 tracking-tight flex items-center gap-2">
                  HOW THE AGENT CLOSED THE LOOP
                  <span className="px-2.5 py-0.5 rounded-full text-xs bg-indigo-500/30 text-indigo-300 font-mono font-bold">
                    {autoResolvedCases.length} AUTO-RESOLVED CASES
                  </span>
                </h2>
                <p className="text-xs text-indigo-300/80 mt-0.5">
                  The AI Agent retrieved source adjustments that mathematically accounted for initial Phase 1 discrepancies.
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {autoResolvedCases.map((item) => (
              <div
                key={item.transaction_id}
                onClick={() => onSelectException(item.transaction_id)}
                className="bg-slate-900/90 border border-indigo-500/30 hover:border-indigo-500/60 p-4 rounded-xl cursor-pointer transition-all hover:bg-slate-900 group"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-xs text-slate-100 group-hover:text-indigo-300 transition-colors">
                    {item.transaction_id}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    <CheckCircle2 className="h-3 w-3 text-emerald-400" /> AUTO RESOLVED
                  </span>
                </div>
                <p className="text-xs text-slate-300 mt-2 line-clamp-2 leading-relaxed">
                  {item.reason}
                </p>
                <div className="mt-3 flex items-center justify-between text-[11px] text-indigo-400 font-medium">
                  <span>View Adjustment Evidence</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. NEEDS HUMAN REVIEW SECTION */}
      <div className="bg-amber-950/20 border border-amber-500/30 rounded-2xl p-6 shadow-md relative overflow-hidden backdrop-blur-md">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-amber-500/20">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-base font-bold text-amber-200 tracking-tight flex items-center gap-2">
                NEEDS HUMAN REVIEW
                <span className="px-2.5 py-0.5 rounded-full text-xs bg-amber-500/30 text-amber-300 font-mono font-bold">
                  {humanReviewCases.length} CASES REQUIRE ATTENTION
                </span>
              </h2>
              <p className="text-xs text-amber-300/80 mt-0.5">
                Escalated safely due to missing records or unexplained gaps with zero matching adjustments.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(categoryCounts).map(([cat, count]) => (
            <div
              key={cat}
              className="flex items-center gap-2 bg-amber-950/60 border border-amber-500/30 px-3 py-1.5 rounded-xl text-xs"
            >
              <span className="text-amber-200 font-medium">{cat.replace(/_/g, ' ')}</span>
              <span className="font-mono font-bold bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded-md">
                {count}
              </span>
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {humanReviewCases.slice(0, 6).map((item) => (
            <div
              key={item.transaction_id}
              onClick={() => onSelectException(item.transaction_id)}
              className="bg-slate-900/90 border border-amber-500/20 hover:border-amber-500/50 p-3.5 rounded-xl cursor-pointer transition-all hover:bg-slate-900 group"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-xs text-slate-100 group-hover:text-amber-300 transition-colors">
                  {item.transaction_id}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  {item.exception_type}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-2 line-clamp-2 leading-relaxed">
                {item.reason}
              </p>
              <div className="mt-3 flex items-center justify-between text-[11px] text-amber-400/90 font-medium">
                <span>Inspect Evidence</span>
                <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
