import React from 'react';
import { Zap, Clock } from 'lucide-react';

export default function ResolutionBars({ metrics }) {
  if (!metrics) {
    return (
      <div className="bg-background border border-border rounded-lg p-6 text-center shadow-xs">
        <p className="text-sm font-semibold text-text">No stage progression metrics</p>
        <p className="text-xs text-text-secondary mt-1">
          Resolution breakdown and processing throughput will appear once a run completes.
        </p>
      </div>
    );
  }

  const initialMatchRate = metrics.initial_match_rate ?? 0.0;
  const finalResolutionRate = metrics.final_resolution_rate ?? 0.0;
  const agentResolutionRate = metrics.agent_resolution_rate ?? metrics.ai_resolution_rate ?? 0.0;
  const procTime = metrics.total_processing_time_sec ?? metrics.phase1_time_sec ?? 0.0;
  const throughput = metrics.records_per_second ?? 0.0;

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
    <div className="bg-background border border-border rounded-lg p-6 flex flex-col justify-between shadow-xs">
      {/* Panel Header */}
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div>
          <h2 className="text-sm font-semibold text-text">
            Reconciliation Performance
          </h2>
          <p className="text-xs text-text-secondary mt-0.5">
            Stage progression and throughput metrics
          </p>
        </div>

        {/* Throughput & Latency badge */}
        <div className="flex items-center gap-3 text-xs font-mono bg-surface border border-border px-3 py-1.5 rounded-lg">
          <div className="flex items-center gap-1 text-text">
            <Zap className="h-3.5 w-3.5 text-primary" />
            <span className="font-semibold">{throughput.toFixed(1)}</span>
            <span className="text-text-secondary text-[11px]">rec/s</span>
          </div>
          <span className="text-border">|</span>
          <div className="flex items-center gap-1 text-text">
            <Clock className="h-3.5 w-3.5 text-text-secondary/60" />
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
                <span className="font-medium text-text">{row.title}</span>
                <span className="text-text-secondary/60 text-[11px] hidden sm:inline">({row.description})</span>
              </div>
              <span className="font-mono font-semibold text-xs text-text">
                {row.value.toFixed(1)}%
              </span>
            </div>

            {/* Progress track */}
            <div className="h-2 w-full bg-surface-alt rounded-full overflow-hidden border border-border">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${Math.min(Math.max(row.value, 0), 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
