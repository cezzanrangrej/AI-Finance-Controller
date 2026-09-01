import React from 'react';
import { Layers, Play, CheckCircle2, AlertTriangle, ArrowUpRight, Clock } from 'lucide-react';

export default function RunsView({ runs, activeRunId, onSelectRun, onTriggerRun, isRunning }) {
  return (
    <div className="bg-background rounded-lg border border-border shadow-xs p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-border gap-4">
        <div>
          <h2 className="text-base font-semibold text-text">Reconciliation Execution Runs</h2>
          <p className="text-xs text-text-secondary mt-0.5">
            Audit history of batch runs, matching benchmarks, and AI auto-resolution decisions.
          </p>
        </div>

        <button
          onClick={onTriggerRun}
          disabled={isRunning}
          className="px-4 py-2 bg-primary hover:bg-primary-light text-white text-xs font-medium rounded-lg shadow-xs transition-colors flex items-center gap-2 disabled:opacity-50 cursor-pointer"
        >
          <Play className="h-3.5 w-3.5 fill-current" />
          <span>{isRunning ? 'Executing...' : 'New Reconciliation Run'}</span>
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-border bg-surface text-text-secondary font-semibold text-[11px] uppercase tracking-wider">
              <th className="py-3 px-4">Run ID</th>
              <th className="py-3 px-4">Timestamp</th>
              <th className="py-3 px-4">Architecture / Provider</th>
              <th className="py-3 px-4 text-right">Total Records</th>
              <th className="py-3 px-4 text-right">Initial Match</th>
              <th className="py-3 px-4 text-right">AI Resolved</th>
              <th className="py-3 px-4 text-right">Human Review</th>
              <th className="py-3 px-4 text-right">Final Resolution</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-normal text-text-secondary">
            {(!runs || runs.length === 0) ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-text-secondary/60 font-medium">
                  No reconciliation runs recorded yet.
                </td>
              </tr>
            ) : (
              runs.map((r) => {
                const isActive = r.run_id === activeRunId;
                return (
                  <tr
                    key={r.run_id}
                    className={`hover:bg-surface transition-colors ${
                      isActive ? 'bg-primary/5 font-medium' : ''
                    }`}
                  >
                    <td className="py-3 px-4 font-mono font-semibold text-text">
                      <div className="flex items-center gap-2">
                        {isActive && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
                        <span>{r.run_id}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-text-secondary font-mono text-[11px]">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-surface-alt text-text-secondary border border-border">
                        Multi-Agent · {r.llm_provider || 'demo'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-text">
                      {r.total_records}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-text-secondary">
                      {r.initial_reconciled} ({r.initial_match_rate?.toFixed(1)}%)
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-primary font-semibold">
                      {r.ai_auto_resolved}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-accent-coral font-semibold">
                      {r.human_review}
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-text">
                      {r.final_resolution_rate?.toFixed(1)}%
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <a
                          href={`/api/runs/${r.run_id}/report?format=markdown&download=true`}
                          download={`reconciliation_report_${r.run_id}.md`}
                          title="Download Markdown Report"
                          className="px-2.5 py-1 rounded text-xs font-medium bg-background border border-border text-text hover:bg-surface transition-colors inline-flex items-center gap-1 cursor-pointer"
                        >
                          <span>Report</span>
                        </a>
                        <button
                          onClick={() => onSelectRun && onSelectRun(r.run_id)}
                          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer ${
                            isActive
                              ? 'bg-primary text-white shadow-xs'
                              : 'bg-background border border-border text-text hover:bg-surface'
                          }`}
                        >
                          {isActive ? 'Active' : 'View Details'}
                        </button>
                      </div>
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
