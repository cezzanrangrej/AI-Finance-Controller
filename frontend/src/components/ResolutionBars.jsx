import React from 'react';
import { Gauge, Zap, Clock } from 'lucide-react';

export default function ResolutionBars({ metrics }) {
  if (!metrics) return null;

  const initialMatchRate = metrics.initial_match_rate || 70.0;
  const finalResolutionRate = metrics.final_resolution_rate || 70.0;
  const agentResolutionRate = metrics.agent_resolution_rate || 0.0;
  const procTime = metrics.total_processing_time_sec || 0.05;
  const throughput = metrics.records_per_second || 2000.0;

  const items = [
    {
      title: 'Initial Match Rate',
      value: initialMatchRate,
      color: 'bg-emerald-500',
      textColor: 'text-emerald-400',
      description: 'Phase 1 deterministic rule matching',
    },
    {
      title: 'Final Resolution Rate',
      value: finalResolutionRate,
      color: 'bg-indigo-500',
      textColor: 'text-indigo-400',
      description: 'Combined Phase 1 + Phase 2 AI resolution',
    },
    {
      title: 'Agent Resolution Rate',
      value: agentResolutionRate,
      color: 'bg-purple-500',
      textColor: 'text-purple-400',
      description: 'Exceptions auto-resolved with evidence',
    },
  ];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-sm backdrop-blur-sm">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-base font-bold text-slate-100">Reconciliation Resolution Performance</h2>
          <p className="text-xs text-slate-400 mt-0.5">Real-time match rate metrics and processing throughput</p>
        </div>

        {/* Throughput Badge */}
        <div className="flex items-center gap-4 text-xs font-mono bg-slate-950/80 border border-slate-800 px-3.5 py-2 rounded-xl">
          <div className="flex items-center gap-1.5 text-indigo-400">
            <Zap className="h-3.5 w-3.5" />
            <span className="font-bold">{throughput.toFixed(1)}</span>
            <span className="text-slate-500">rec/sec</span>
          </div>
          <div className="h-3 w-[1px] bg-slate-800" />
          <div className="flex items-center gap-1.5 text-slate-300">
            <Clock className="h-3.5 w-3.5 text-slate-500" />
            <span>{procTime.toFixed(3)}s</span>
          </div>
        </div>
      </div>

      <div className="space-y-5">
        {items.map((item, idx) => (
          <div key={idx} className="space-y-1.5">
            <div className="flex justify-between items-baseline text-xs">
              <span className="font-semibold text-slate-200">{item.title}</span>
              <div className="flex items-center gap-2">
                <span className="text-slate-400 text-[11px]">{item.description}</span>
                <span className={`font-mono font-bold text-sm ${item.textColor}`}>
                  {item.value.toFixed(2)}%
                </span>
              </div>
            </div>

            {/* Progress Bar Container */}
            <div className="h-2.5 w-full bg-slate-950 rounded-full overflow-hidden p-0.5 border border-slate-800/80">
              <div
                className={`h-full rounded-full transition-all duration-700 ${item.color}`}
                style={{ width: `${Math.min(Math.max(item.value, 0), 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
