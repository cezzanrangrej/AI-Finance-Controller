import React from 'react';
import { Zap, Clock } from 'lucide-react';

export default function ResolutionBars({ metrics }) {
  if (!metrics) return null;

  const initialMatchRate = metrics.initial_match_rate ?? 70.0;
  const finalResolutionRate = metrics.final_resolution_rate ?? 70.0;
  const agentResolutionRate = metrics.agent_resolution_rate ?? 0.0;
  const procTime = metrics.total_processing_time_sec ?? 0.04;
  const throughput = metrics.records_per_second ?? 2500.0;

  const rows = [
    {
      title: 'Initial match rate',
      description: 'Phase 1 deterministic rule matching',
      value: initialMatchRate,
    },
    {
      title: 'Final resolution rate',
      description: 'Combined Phase 1 + Phase 2 AI resolution',
      value: finalResolutionRate,
    },
    {
      title: 'AI resolution rate',
      description: 'Exceptions auto-resolved with evidence',
      value: agentResolutionRate,
    },
  ];

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-6 flex flex-col justify-between shadow-xs">
      {/* Panel Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Reconciliation Performance
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Stage progression and throughput metrics
          </p>
        </div>

        {/* Throughput & Latency badge */}
        <div className="flex items-center gap-3 text-xs font-mono bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg">
          <div className="flex items-center gap-1 text-slate-700">
            <Zap className="h-3.5 w-3.5 text-emerald-600" />
            <span className="font-semibold">{throughput.toFixed(1)}</span>
            <span className="text-slate-500 text-[11px]">rec/s</span>
          </div>
          <span className="text-slate-300">|</span>
          <div className="flex items-center gap-1 text-slate-700">
            <Clock className="h-3.5 w-3.5 text-slate-400" />
            <span className="font-semibold">{procTime.toFixed(3)}s</span>
          </div>
        </div>
      </div>

      {/* Metric Rows */}
      <div className="space-y-4 pt-4">
        {rows.map((row, idx) => (
          <div key={idx} className="space-y-1.5">
            <div className="flex items-baseline justify-between text-xs">
              <div className="flex items-baseline gap-2">
                <span className="font-medium text-slate-800">{row.title}</span>
                <span className="text-slate-400 text-[11px] hidden sm:inline">({row.description})</span>
              </div>
              <span className="font-mono font-semibold text-xs text-slate-900">
                {row.value.toFixed(1)}%
              </span>
            </div>

            {/* Progress track */}
            <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden border border-slate-200/60">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${Math.min(Math.max(row.value, 0), 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
