import React, { useState, useEffect } from 'react';
import { FileText, Search, Activity, CheckCircle2, ShieldAlert, ArrowRight } from 'lucide-react';
import { fetchAuditLogs } from '../lib/api';

export default function AuditLogView({ activeRunId, onSelectTransaction }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (activeRunId) {
      loadLogs(activeRunId);
    } else {
      // Otherwise a previously loaded trail stays on screen after its run is no
      // longer the active one.
      setLogs([]);
    }
  }, [activeRunId]);

  const loadLogs = async (runId) => {
    try {
      setLoading(true);
      const data = await fetchAuditLogs(runId);
      setLogs(data);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = logs.filter((l) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      l.transaction_id.toLowerCase().includes(q) ||
      l.step.toLowerCase().includes(q) ||
      l.event.toLowerCase().includes(q)
    );
  });

  return (
    <div className="bg-background rounded-lg border border-border shadow-xs p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-border gap-4">
        <div>
          <h2 className="text-base font-semibold text-text">Immutable Audit Trail</h2>
          <p className="text-xs text-text-secondary mt-0.5">
            {activeRunId ? (
              <>
                Step-by-step transaction ingestion, rule verification, and agent investigative actions for Run{' '}
                <span className="font-mono text-text font-medium">{activeRunId}</span>.
              </>
            ) : (
              // No run is active until one completes or the user picks one in the
              // Runs tab, so the sentence must not trail off into a blank id.
              'No run selected. Run a reconciliation, or pick a past run in the Runs tab, to inspect its audit trail.'
            )}
          </p>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-secondary/60" />
          <input
            type="text"
            placeholder="Search TXN ID or event..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-surface border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-text placeholder-text-secondary/60 outline-none focus:border-primary focus:bg-background transition-colors"
          />
        </div>
      </div>

      {loading ? (
        <div className="py-12 text-center text-text-secondary/60 text-xs">
          Loading audit events...
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-text-secondary/60 text-xs">
          No audit events recorded for this run.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border bg-surface text-text-secondary font-semibold text-[11px] uppercase tracking-wider">
                <th className="py-3 px-4">Transaction ID</th>
                <th className="py-3 px-4">Audit Step</th>
                <th className="py-3 px-4">Lifecycle Status</th>
                <th className="py-3 px-4">Investigative Event</th>
                <th className="py-3 px-4 text-center">Confidence</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-normal text-text-secondary">
              {filtered.map((log, idx) => (
                <tr
                  key={idx}
                  onClick={() => onSelectTransaction && onSelectTransaction(log.transaction_id)}
                  className="hover:bg-surface cursor-pointer transition-colors group"
                >
                  <td className="py-3 px-4 font-mono font-semibold text-text group-hover:text-primary">
                    {log.transaction_id}
                  </td>
                  <td className="py-3 px-4 font-mono text-[11px] text-text-secondary">
                    {log.step}
                  </td>
                  <td className="py-3 px-4">
                    <span className={`inline-flex items-center gap-1 text-[10px] font-mono font-semibold px-2 py-0.5 rounded border ${
                      log.status === 'RECONCILED' || log.status === 'AUTO_RESOLVED'
                        ? 'bg-accent-green/10 text-text border-accent-green/30'
                        : 'bg-accent-coral/10 text-text border-accent-coral/30'
                    }`}>
                      {log.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-text">
                    {log.event}
                  </td>
                  <td className="py-3 px-4 text-center font-mono text-[11px] text-text">
                    {log.confidence != null ? `${(log.confidence * 100).toFixed(0)}%` : '—'}
                  </td>
                  <td className="py-3 px-4 text-right text-text-secondary/60 group-hover:text-primary">
                    <ArrowRight className="h-4 w-4 ml-auto" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
