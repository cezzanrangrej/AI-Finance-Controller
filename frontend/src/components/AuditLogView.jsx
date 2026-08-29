import React, { useState, useEffect } from 'react';
import { FileText, Search, Activity, CheckCircle2, ShieldAlert, ArrowRight } from 'lucide-react';

export default function AuditLogView({ activeRunId, onSelectTransaction }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (activeRunId) {
      fetchAuditLogs(activeRunId);
    }
  }, [activeRunId]);

  const fetchAuditLogs = async (runId) => {
    try {
      setLoading(true);
      const res = await fetch(`/api/runs/${runId}/audit`);
      if (res.ok) {
        setLogs(await res.json());
      }
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
    <div className="bg-white rounded-lg border border-slate-200 shadow-xs p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-200 gap-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Immutable Audit Trail</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Step-by-step transaction ingestion, rule verification, and agent investigative actions for Run <span className="font-mono text-slate-700">{activeRunId}</span>.
          </p>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search TXN ID or event..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 outline-none focus:border-emerald-500 focus:bg-white transition-colors"
          />
        </div>
      </div>

      {loading ? (
        <div className="py-12 text-center text-slate-400 text-xs">
          Loading audit events...
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-slate-400 text-xs">
          No audit events recorded for this run.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-slate-500 font-semibold text-[11px] uppercase tracking-wider">
                <th className="py-3 px-4">Transaction ID</th>
                <th className="py-3 px-4">Audit Step</th>
                <th className="py-3 px-4">Lifecycle Status</th>
                <th className="py-3 px-4">Investigative Event</th>
                <th className="py-3 px-4 text-center">Confidence</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-normal text-slate-600">
              {filtered.map((log, idx) => (
                <tr
                  key={idx}
                  onClick={() => onSelectTransaction(log.transaction_id)}
                  className="hover:bg-slate-50 cursor-pointer transition-colors group"
                >
                  <td className="py-3 px-4 font-mono font-semibold text-slate-900 group-hover:text-emerald-600">
                    {log.transaction_id}
                  </td>
                  <td className="py-3 px-4 font-mono text-[11px] text-slate-500">
                    {log.step}
                  </td>
                  <td className="py-3 px-4">
                    <span className={`inline-flex items-center gap-1 text-[10px] font-mono font-semibold px-2 py-0.5 rounded ${
                      log.status === 'RECONCILED' || log.status === 'AUTO_RESOLVED'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border border-amber-200'
                    }`}>
                      {log.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-slate-700">
                    {log.event}
                  </td>
                  <td className="py-3 px-4 text-center font-mono text-[11px]">
                    {log.confidence != null ? `${(log.confidence * 100).toFixed(0)}%` : '—'}
                  </td>
                  <td className="py-3 px-4 text-right text-slate-400 group-hover:text-emerald-600">
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
