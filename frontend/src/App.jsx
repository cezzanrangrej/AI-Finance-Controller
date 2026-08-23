import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import KPICards from './components/KPICards';
import ResolutionBars from './components/ResolutionBars';
import ExceptionChart from './components/ExceptionChart';
import HumanReviewSection from './components/HumanReviewSection';
import EvaluationPanel from './components/EvaluationPanel';
import ReconciliationTable from './components/ReconciliationTable';
import ExceptionDetailModal from './components/ExceptionDetailModal';

export default function App() {
  const [runs, setRuns] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [selectedTxnDetail, setSelectedTxnDetail] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch runs list on mount
  useEffect(() => {
    fetchRuns();
  }, []);

  // Fetch details when activeRunId changes
  useEffect(() => {
    if (activeRunId) {
      fetchRunDetails(activeRunId);
    }
  }, [activeRunId]);

  const fetchRuns = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/runs');
      if (res.ok) {
        const data = await res.json();
        setRuns(data);
        if (data.length > 0) {
          setActiveRunId(data[0].run_id);
        } else {
          // If no runs exist yet, trigger initial run
          triggerRun();
        }
      } else {
        // Fallback demo run trigger
        triggerRun();
      }
    } catch (err) {
      console.warn('API error, executing initial run...', err);
      triggerRun();
    } finally {
      setLoading(false);
    }
  };

  const fetchRunDetails = async (runId) => {
    try {
      const [mRes, tRes, eRes] = await Promise.all([
        fetch(`/api/runs/${runId}/metrics`),
        fetch(`/api/runs/${runId}/transactions`),
        fetch(`/api/runs/${runId}/exceptions`),
      ]);

      if (mRes.ok) setMetrics(await mRes.json());
      if (tRes.ok) setTransactions(await tRes.json());
      if (eRes.ok) setExceptions(await eRes.json());
    } catch (err) {
      console.error('Failed to fetch run details:', err);
    }
  };

  const triggerRun = async () => {
    try {
      setIsRunning(true);
      setError(null);
      const res = await fetch('/api/runs', { method: 'POST' });
      if (res.ok) {
        const newRun = await res.json();
        setActiveRunId(newRun.run_id);
        // Refresh runs list
        const listRes = await fetch('/api/runs');
        if (listRes.ok) {
          setRuns(await listRes.json());
        }
      } else {
        setError('Failed to execute reconciliation run');
      }
    } catch (err) {
      setError('Network error running reconciliation');
      console.error(err);
    } finally {
      setIsRunning(false);
      setLoading(false);
    }
  };

  const handleSelectTransaction = async (txnId) => {
    if (!activeRunId) return;
    try {
      const res = await fetch(`/api/runs/${activeRunId}/transactions/${txnId}`);
      if (res.ok) {
        setSelectedTxnDetail(await res.json());
      }
    } catch (err) {
      console.error('Failed to load transaction detail:', err);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans pb-16">
      {/* Header */}
      <Header
        onRun={triggerRun}
        isRunning={isRunning}
        activeRunId={activeRunId}
        runs={runs}
        onSelectRun={setActiveRunId}
      />

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-6 pt-8 space-y-8 flex-1 w-full">
        
        {/* Error notification */}
        {error && (
          <div className="p-4 rounded-xl bg-red-950/40 border border-red-500/30 text-red-300 text-xs font-semibold">
            {error}
          </div>
        )}

        {/* Loading overlay */}
        {loading && !metrics && (
          <div className="p-12 text-center text-slate-400 font-medium space-y-3">
            <div className="h-8 w-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p className="text-xs font-mono">Loading reconciliation metrics and API data...</p>
          </div>
        )}

        {metrics && (
          <>
            {/* KPI Summary Cards */}
            <KPICards metrics={metrics} />

            {/* Performance Bars & Exception Breakdown Chart */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <ResolutionBars metrics={metrics} />
              <ExceptionChart breakdown={metrics.exception_breakdown} />
            </div>

            {/* Dedicated Needs Human Review Section */}
            <HumanReviewSection
              exceptions={exceptions}
              onSelectException={handleSelectTransaction}
            />

            {/* Evaluation & Accuracy Panel */}
            <EvaluationPanel metrics={metrics} />

            {/* Searchable Reconciliation Table */}
            <ReconciliationTable
              transactions={transactions}
              exceptions={exceptions}
              onSelectTransaction={handleSelectTransaction}
            />
          </>
        )}
      </main>

      {/* Transaction / Exception Detail Modal */}
      {selectedTxnDetail && (
        <ExceptionDetailModal
          detail={selectedTxnDetail}
          onClose={() => setSelectedTxnDetail(null)}
        />
      )}

      {/* Footer */}
      <footer className="max-w-7xl mx-auto px-6 pt-12 text-xs text-slate-500 flex flex-col sm:flex-row justify-between items-center gap-4 border-t border-slate-900 mt-12 w-full">
        <div>
          <span className="font-semibold text-slate-400">AI Finance Controller</span> — Phase 3 Demo Stack
        </div>
        <div className="font-mono text-[11px] text-slate-600">
          Phase 1 = Deterministic Truth | Phase 2 = AI Investigation | Phase 3 = API & Dashboard
        </div>
      </footer>
    </div>
  );
}
