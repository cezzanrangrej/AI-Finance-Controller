import React from 'react';
import { Layers, Play, CheckCircle2, AlertTriangle, ArrowUpRight, Clock } from 'lucide-react';

export default function RunsView({ runs, activeRunId, onSelectRun, onTriggerRun, isRunning }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 shadow-xs p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-200 gap-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Reconciliation Execution Runs</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Audit history of batch runs, matching benchmarks, and AI auto-resolution decisions.
          </p>
        </div>

        <button
          onClick={onTriggerRun}
          disabled={isRunning}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg shadow-xs transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5 fill-current" />
          <span>{isRunning ? 'Executing...' : 'New Reconciliation Run'}</span>
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-slate-500 font-semibold text-[11px] uppercase tracking-wider">
              <th className="py-3 px-4">Run ID</th>
              <th className="py-3 px-4">Timestamp</th>
              <th className="py-3 px-4">Provider / Mode</th>
              <th className="py-3 px-4 text-right">Total Records</th>
              <th className="py-3 px-4 text-right">Initial Match</th>
              <th className="py-3 px-4 text-right">AI Resolved</th>
              <th className="py-3 px-4 text-right">Human Review</th>
              <th className="py-3 px-4 text-right">Final Resolution</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-normal text-slate-600">
            {(!runs || runs.length === 0) ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-slate-400 font-medium">
                  No reconciliation runs recorded yet.
                </td>
              </tr>
            ) : (
              runs.map((r) => {
                const isActive = r.run_id === activeRunId;
                return (
                  <tr
                    key={r.run_id}
                    className={`hover:bg-slate-50 transition-colors ${
                      isActive ? 'bg-emerald-50/40 font-medium' : ''
                    }`}
                  >
                    <td className="py-3 px-4 font-mono font-semibold text-slate-900">
                      <div className="flex items-center gap-2">
                        {isActive && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />}
                        <span>{r.run_id}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-slate-500 font-mono text-[11px]">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                        {r.llm_provider || 'demo'} · {r.llm_mode || 'DEMO'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-slate-900">
                      {r.total_records}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-slate-700">
                      {r.initial_reconciled} ({r.initial_match_rate?.toFixed(1)}%)
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-emerald-600 font-semibold">
                      {r.ai_auto_resolved}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-amber-600 font-semibold">
                      {r.human_review}
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-slate-900">
                      {r.final_resolution_rate?.toFixed(1)}%
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => onSelectRun(r.run_id)}
                        className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                          isActive
                            ? 'bg-emerald-600 text-white shadow-xs'
                            : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                        }`}
                      >
                        {isActive ? 'Active' : 'View Details'}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
