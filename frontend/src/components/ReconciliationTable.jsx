import React, { useState, useMemo } from 'react';
import { Search, Filter, ChevronRight, CheckCircle2, AlertCircle, Bot, ShieldAlert } from 'lucide-react';

export default function ReconciliationTable({ transactions, exceptions, onSelectTransaction }) {
  const [activeTab, setActiveTab] = useState('ALL'); // ALL, RECONCILED, AUTO_RESOLVED, HUMAN_REVIEW
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');

  // Build unified items list
  const unifiedItems = useMemo(() => {
    if (!transactions) return [];

    const excMap = new Map();
    if (exceptions) {
      exceptions.forEach((e) => excMap.set(e.transaction_id, e));
    }

    return transactions.map((t) => {
      const exc = excMap.get(t.transaction_id);
      const isReconciled = t.status === 'RECONCILED';

      let decision = 'N/A';
      if (!isReconciled) {
        decision = exc?.decision || 'HUMAN_REVIEW';
      }

      return {
        transaction_id: t.transaction_id,
        status: t.status,
        exception_type: t.exception_type || 'None',
        decision: decision,
        amount: t.payment_amount || t.gross_amount || 0,
        difference: t.difference,
        confidence: exc?.confidence ?? (isReconciled ? 1.0 : 0.0),
        reason: exc?.reason || (isReconciled ? 'Reconciled successfully' : 'Pending review'),
        raw: t,
      };
    });
  }, [transactions, exceptions]);

  // Filtered dataset
  const filteredData = useMemo(() => {
    return unifiedItems.filter((item) => {
      // Tab filter
      if (activeTab === 'RECONCILED' && item.status !== 'RECONCILED') return false;
      if (activeTab === 'AUTO_RESOLVED' && item.decision !== 'AUTO_RESOLVED') return false;
      if (activeTab === 'HUMAN_REVIEW' && item.decision !== 'HUMAN_REVIEW') return false;

      // Category filter
      if (categoryFilter !== 'ALL' && item.exception_type !== categoryFilter) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          item.transaction_id.toLowerCase().includes(q) ||
          item.exception_type.toLowerCase().includes(q) ||
          item.reason.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [unifiedItems, activeTab, categoryFilter, searchQuery]);

  // Exception categories for dropdown
  const categories = useMemo(() => {
    const set = new Set();
    unifiedItems.forEach((item) => {
      if (item.exception_type && item.exception_type !== 'None') {
        set.add(item.exception_type);
      }
    });
    return Array.from(set);
  }, [unifiedItems]);

  const tabs = [
    { key: 'ALL', label: 'All Transactions', count: unifiedItems.length },
    { key: 'RECONCILED', label: 'Reconciled', count: unifiedItems.filter((i) => i.status === 'RECONCILED').length },
    { key: 'AUTO_RESOLVED', label: 'Auto-Resolved', count: unifiedItems.filter((i) => i.decision === 'AUTO_RESOLVED').length },
    { key: 'HUMAN_REVIEW', label: 'Needs Human Review', count: unifiedItems.filter((i) => i.decision === 'HUMAN_REVIEW').length },
  ];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl shadow-sm backdrop-blur-sm overflow-hidden">
      {/* Table Header & Controls */}
      <div className="p-6 border-b border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-100">Reconciliation Ledger & Decisions</h2>
            <p className="text-xs text-slate-400 mt-0.5">Filter, search, and inspect individual transaction decisions</p>
          </div>

          {/* Search Input */}
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search TXN ID, exception..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        {/* Filter Tabs & Dropdown */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
          {/* Tabs */}
          <div className="flex flex-wrap items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  activeTab === tab.key
                    ? 'bg-slate-800 text-white shadow-sm font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                {tab.label}
                <span className="ml-1.5 font-mono text-[10px] px-1.5 py-0.2 rounded bg-slate-900 text-slate-400 border border-slate-700/50">
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {/* Category Dropdown */}
          <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-xl text-xs">
            <Filter className="h-3.5 w-3.5 text-slate-500" />
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="bg-transparent text-slate-300 font-medium outline-none cursor-pointer"
            >
              <option value="ALL" className="bg-slate-900 text-slate-200">All Exceptions</option>
              {categories.map((cat) => (
                <option key={cat} value={cat} className="bg-slate-900 text-slate-200">
                  {cat.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Table Data */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-950/50 text-slate-400 font-semibold uppercase tracking-wider text-[11px]">
              <th className="py-3.5 px-6">Transaction ID</th>
              <th className="py-3.5 px-4">Initial Status</th>
              <th className="py-3.5 px-4">Exception Category</th>
              <th className="py-3.5 px-4">AI Decision</th>
              <th className="py-3.5 px-4 text-right">Amount</th>
              <th className="py-3.5 px-4 text-right">Difference</th>
              <th className="py-3.5 px-4 text-center">Confidence</th>
              <th className="py-3.5 px-6 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-medium text-slate-300">
            {filteredData.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-500 font-medium">
                  No matching transaction records found.
                </td>
              </tr>
            ) : (
              filteredData.map((item) => (
                <tr
                  key={item.transaction_id}
                  onClick={() => onSelectTransaction(item.transaction_id)}
                  className="hover:bg-slate-800/40 cursor-pointer transition-colors group"
                >
                  <td className="py-3.5 px-6 font-mono font-bold text-slate-100 group-hover:text-indigo-400 transition-colors">
                    {item.transaction_id}
                  </td>
                  <td className="py-3.5 px-4">
                    {item.status === 'RECONCILED' ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="h-3 w-3" /> RECONCILED
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        <AlertCircle className="h-3 w-3" /> EXCEPTION
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 font-mono text-[11px] text-slate-400">
                    {item.exception_type !== 'None' ? item.exception_type : '-'}
                  </td>
                  <td className="py-3.5 px-4">
                    {item.decision === 'AUTO_RESOLVED' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                        <Bot className="h-3 w-3" /> AUTO RESOLVED
                      </span>
                    )}
                    {item.decision === 'HUMAN_REVIEW' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        <ShieldAlert className="h-3 w-3" /> HUMAN REVIEW
                      </span>
                    )}
                    {item.decision === 'N/A' && (
                      <span className="text-slate-500 text-[11px]">N/A</span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 text-right font-mono text-slate-200">
                    ₹{item.amount.toLocaleString()}
                  </td>
                  <td className="py-3.5 px-4 text-right font-mono">
                    {item.difference != null && item.difference !== 0 ? (
                      <span className={item.difference > 0 ? 'text-amber-400' : 'text-purple-400'}>
                        ₹{item.difference.toLocaleString()}
                      </span>
                    ) : (
                      <span className="text-slate-500">₹0</span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 text-center font-mono text-xs">
                    {item.decision !== 'N/A' ? (
                      <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300">
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    ) : (
                      <span className="text-slate-600">-</span>
                    )}
                  </td>
                  <td className="py-3.5 px-6 text-right text-indigo-400">
                    <ChevronRight className="h-4 w-4 ml-auto transition-transform group-hover:translate-x-1" />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="p-4 border-t border-slate-800 bg-slate-950/40 text-xs text-slate-500 flex justify-between items-center">
        <span>Showing {filteredData.length} of {unifiedItems.length} records</span>
        <span>Click any row for multi-source detail & AI audit trail</span>
      </div>
    </div>
  );
}
