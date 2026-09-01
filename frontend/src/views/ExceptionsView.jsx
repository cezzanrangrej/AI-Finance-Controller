import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, Bot, ShieldAlert, ArrowUpRight, Search, Filter } from 'lucide-react';

export default function ExceptionsView({ exceptions, onSelectTransaction }) {
  const [filterType, setFilterType] = useState('ALL'); // ALL, HUMAN_REVIEW, AUTO_RESOLVED
  const [search, setSearch] = useState('');

  if (!exceptions) {
    return (
      <div className="bg-background rounded-lg border border-border p-8 text-center text-text-secondary/60 text-xs">
        No exception data loaded.
      </div>
    );
  }

  const filtered = exceptions.filter((e) => {
    if (filterType === 'HUMAN_REVIEW' && e.decision !== 'HUMAN_REVIEW') return false;
    if (filterType === 'AUTO_RESOLVED' && e.decision !== 'AUTO_RESOLVED') return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return (
        e.transaction_id.toLowerCase().includes(q) ||
        e.exception_type.toLowerCase().includes(q) ||
        e.reason.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const humanReviewCount = exceptions.filter((e) => e.decision === 'HUMAN_REVIEW').length;
  const autoResolvedCount = exceptions.filter((e) => e.decision === 'AUTO_RESOLVED').length;

  return (
    <div className="space-y-6">
      <div className="bg-background rounded-lg border border-border p-6 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-border gap-4">
          <div>
            <h2 className="text-base font-semibold text-text">Exception Triage & Investigation Queue</h2>
            <p className="text-xs text-text-secondary mt-0.5">
              Review cases requiring finance ops attention and inspect deterministic proof on auto-resolved exceptions.
            </p>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-secondary/60" />
            <input
              type="text"
              placeholder="Search exception..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-surface border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-text placeholder-text-secondary/60 outline-none focus:border-primary focus:bg-background transition-colors"
            />
          </div>
        </div>

        {/* Filter Toolbar */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilterType('ALL')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filterType === 'ALL'
                ? 'bg-primary text-white shadow-xs font-semibold'
                : 'bg-surface-alt text-text-secondary hover:text-text'
            }`}
          >
            All Exceptions ({exceptions.length})
          </button>
          <button
            onClick={() => setFilterType('HUMAN_REVIEW')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border ${
              filterType === 'HUMAN_REVIEW'
                ? 'bg-accent-coral text-text shadow-xs font-semibold border-accent-coral'
                : 'bg-accent-coral/10 text-text hover:bg-accent-coral/20 border-accent-coral/30'
            }`}
          >
            Needs Human Review ({humanReviewCount})
          </button>
          <button
            onClick={() => setFilterType('AUTO_RESOLVED')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border ${
              filterType === 'AUTO_RESOLVED'
                ? 'bg-accent-green text-text shadow-xs font-semibold border-accent-green'
                : 'bg-accent-green/10 text-text hover:bg-accent-green/20 border-accent-green/30'
            }`}
          >
            Auto-Resolved ({autoResolvedCount})
          </button>
        </div>
      </div>

      {/* Exceptions Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((item) => {
          const isResolved = item.decision === 'AUTO_RESOLVED';
          return (
            <div
              key={item.transaction_id}
              onClick={() => onSelectTransaction && onSelectTransaction(item.transaction_id)}
              className="bg-background border border-border hover:border-border rounded-lg p-5 shadow-xs cursor-pointer transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-xs text-text group-hover:text-primary transition-colors">
                    {item.transaction_id}
                  </span>
                  <span className={`inline-flex items-center gap-1 text-[10px] font-mono font-semibold px-2 py-0.5 rounded border ${
                    isResolved
                      ? 'bg-accent-green/10 text-text border-accent-green/30'
                      : 'bg-accent-coral/10 text-text border-accent-coral/30'
                  }`}>
                    {isResolved ? <CheckCircle2 className="h-3 w-3 text-text" /> : <AlertTriangle className="h-3 w-3 text-accent-coral" />}
                    {item.decision}
                  </span>
                </div>

                <div className="text-[11px] font-mono text-text-secondary mt-1">
                  {item.exception_type}
                </div>

                <p className="text-xs text-text-secondary mt-2.5 line-clamp-3 leading-relaxed">
                  {item.reason}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-xs font-medium text-text group-hover:text-primary">
                <span>View Full Audit Snapshot</span>
                <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
