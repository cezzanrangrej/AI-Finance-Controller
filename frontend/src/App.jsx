import React, { useState, useEffect, useRef } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import KPICards from './components/KPICards';
import ResolutionBars from './components/ResolutionBars';
import ExceptionChart from './components/ExceptionChart';
import ReconciliationTable from './components/ReconciliationTable';
import HumanReviewSection from './components/HumanReviewSection';
import EvaluationPanel from './components/EvaluationPanel';
import DataSourcesSection from './components/DataSourcesSection';
import RunsView from './components/RunsView';
import ExceptionsView from './components/ExceptionsView';
import AuditLogView from './components/AuditLogView';
import SettingsView from './components/SettingsView';
import ExceptionDetailModal from './components/ExceptionDetailModal';
import { CheckCircle2, AlertCircle } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [runs, setRuns] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [selectedTxnDetail, setSelectedTxnDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notification, setNotification] = useState(null);

  // Active SSE EventSource reference to guarantee 1 stream connection per run
  const activeEventSourceRef = useRef(null);

  // Advanced developer settings
  const [settings, setSettings] = useState({
    provider: 'openrouter',
    mode: 'batch',
    batchSize: 5,
  });

  // User upload CSV files state
  const [files, setFiles] = useState({
    payments: null,
    ledger: null,
    bank: null,
    adjustments: null,
  });

  // Explicit Workflow State Machine: IDLE | DATA_LOADED | VALIDATING | READY | RUNNING_PHASE_1 | RUNNING_AI | COMPLETED | FAILED
  const [workflowState, setWorkflowState] = useState('READY');

  // Progressive streaming evaluation state
  const [streamingState, setStreamingState] = useState(null);

  // Clean up active EventSource stream on unmount
  useEffect(() => {
    return () => {
      if (activeEventSourceRef.current) {
        activeEventSourceRef.current.close();
        activeEventSourceRef.current = null;
      }
    };
  }, []);

  // Single Primary Action: RUN RECONCILIATION
  const handleRunReconciliation = async () => {
    // 1. Idempotency Guard: prevent duplicate submissions while run is active
    if (workflowState === 'RUNNING_PHASE_1' || workflowState === 'RUNNING_AI' || workflowState === 'VALIDATING') {
      console.warn('[FRONTEND GUARD] Reconciliation already in progress. Ignoring duplicate submission.');
      return;
    }

    const t0 = performance.now();
    console.log('[FRONTEND] Run clicked');

    try {
      setError(null);
      setNotification(null);

      // Clean up any existing active stream before starting a new run
      if (activeEventSourceRef.current) {
        activeEventSourceRef.current.close();
        activeEventSourceRef.current = null;
      }

      const hasCustomFiles = Boolean(files.payments && files.ledger && files.bank);

      if (hasCustomFiles) {
        // Workflow State: UPLOADING -> VALIDATING -> COMPLETED
        setWorkflowState('UPLOADING');

        console.log('[FRONTEND] POST /api/runs/upload sent');
        const t1 = performance.now();

        const formData = new FormData();
        formData.append('payments', files.payments);
        formData.append('ledger', files.ledger);
        formData.append('bank', files.bank);
        if (files.adjustments) formData.append('adjustments', files.adjustments);

        setWorkflowState('VALIDATING');

        const res = await fetch('/api/runs/upload', {
          method: 'POST',
          body: formData,
        });

        const t2 = performance.now();
        console.log(`[FRONTEND] POST response received elapsed=${((t2 - t1) / 1000).toFixed(4)}s`);

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Failed to process uploaded dataset.');
        }

        const data = await res.json();
        setWorkflowState('COMPLETED');
        setNotification(`Reconciliation completed successfully for uploaded dataset (Run ${data.run_id}).`);

        // Refresh runs and active data
        fetchRuns();
      } else {
        // Standard dataset benchmark evaluation stream
        setWorkflowState('STARTING_RECONCILIATION');

        setStreamingState({
          isStreaming: true,
          status: 'RUNNING',
          currentBatch: 1,
          totalBatches: 3,
          casesCompleted: 0,
          totalCases: 13,
          batches: {},
          error: null,
        });

        console.log('[FRONTEND] POST /api/evaluations/start sent');
        const t1 = performance.now();

        // Trigger asynchronous evaluation stream
        const res = await fetch('/api/evaluations/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider: settings.provider,
            cases_per_run: 13,
            runs: 1,
            batch_size: settings.batchSize,
            mode: settings.mode,
          }),
        });

        const t2 = performance.now();
        console.log(`[FRONTEND] POST response received elapsed=${((t2 - t1) / 1000).toFixed(4)}s`);

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Failed to start reconciliation stream.');
        }

        const startData = await res.json();

        // Open SSE stream
        const sseStart = performance.now();
        const eventSource = new EventSource(startData.stream_url);
        activeEventSourceRef.current = eventSource;

        let firstEventReceived = false;

        eventSource.onopen = () => {
          console.log(`[FRONTEND] SSE connected elapsed=${((performance.now() - sseStart) / 1000).toFixed(4)}s`);
        };

        eventSource.addEventListener('phase1_started', () => {
          setWorkflowState('RUNNING_PHASE_1');
          console.log(`[FRONTEND] Phase 1 started elapsed=${((performance.now() - t0) / 1000).toFixed(4)}s`);
        });

        eventSource.addEventListener('phase1_completed', (e) => {
          const data = JSON.parse(e.data);
          setWorkflowState('RUNNING_AI');
          console.log(`[FRONTEND] phase1_completed received elapsed=${((performance.now() - t0) / 1000).toFixed(4)}s`);
        });

        eventSource.addEventListener('run_started', (e) => {
          const data = JSON.parse(e.data);
          if (!firstEventReceived) {
            firstEventReceived = true;
            console.log(`[FRONTEND] first SSE event received elapsed=${((performance.now() - t0) / 1000).toFixed(4)}s`);
            console.log(`[FRONTEND] AI investigation started elapsed=${((performance.now() - t0) / 1000).toFixed(4)}s`);
          }
          setStreamingState((prev) => ({
            ...prev,
            status: 'RUNNING',
            totalCases: data.total_cases,
            totalBatches: data.total_batches,
          }));
        });

        eventSource.addEventListener('batch_started', (e) => {
          const data = JSON.parse(e.data);
          setStreamingState((prev) => {
            if (!prev) return prev;
            const updatedBatches = { ...(prev.batches || {}) };
            if (data.batch_number) {
              updatedBatches[data.batch_number] = {
                batchNumber: data.batch_number,
                status: 'RUNNING',
                caseCount: data.cases_in_batch,
              };
            }
            return {
              ...prev,
              currentBatch: data.batch_number,
              batches: updatedBatches,
            };
          });
        });

        eventSource.addEventListener('batch_completed', (e) => {
          const data = JSON.parse(e.data);
          setStreamingState((prev) => {
            if (!prev) return prev;
            const completedCount = data.cases_completed || (prev.casesCompleted + (data.decisions ? data.decisions.length : 0));
            const updatedBatches = { ...(prev.batches || {}) };

            if (data.batch_number) {
              updatedBatches[data.batch_number] = {
                batchNumber: data.batch_number,
                status: 'COMPLETED',
                durationSec: data.batch_time_sec,
                caseCount: data.decisions ? data.decisions.length : 0,
              };
            }

            return {
              ...prev,
              casesCompleted: completedCount,
              batches: updatedBatches,
            };
          });

          // Progressive result rendering: append exception decisions immediately as each batch finishes
          if (data.decisions && data.decisions.length > 0) {
            setExceptions((prevExc) => {
              const excMap = new Map((prevExc || []).map((ex) => [ex.transaction_id, ex]));
              data.decisions.forEach((d) => {
                excMap.set(d.transaction_id, {
                  ...excMap.get(d.transaction_id),
                  transaction_id: d.transaction_id,
                  decision: d.decision,
                  reason: d.reason,
                  confidence: d.confidence,
                  resolution_type: d.resolution_type,
                  evidence: d.evidence,
                  recommended_action: d.recommended_action,
                });
              });
              return Array.from(excMap.values());
            });
          }
        });

        eventSource.addEventListener('metrics_updated', (e) => {
          const data = JSON.parse(e.data);
          setMetrics((prev) => prev ? ({
            ...prev,
            phase2_accuracy: data.accuracy,
            auto_resolution_precision: data.precision,
            auto_resolution_recall: data.recall,
          }) : prev);
        });

        eventSource.addEventListener('run_completed', async (e) => {
          if (activeEventSourceRef.current) {
            activeEventSourceRef.current.close();
            activeEventSourceRef.current = null;
          }
          setWorkflowState('COMPLETED');
          setStreamingState((prev) => ({
            ...prev,
            isStreaming: false,
            status: 'COMPLETED',
          }));
          setNotification('Reconciliation completed successfully across all records.');
          fetchRuns();
        });

        eventSource.addEventListener('run_error', (e) => {
          const data = JSON.parse(e.data);
          if (activeEventSourceRef.current) {
            activeEventSourceRef.current.close();
            activeEventSourceRef.current = null;
          }
          setWorkflowState('FAILED');
          setError(data.error || 'Reconciliation failed during batch execution.');
        });

        eventSource.onerror = () => {
          if (activeEventSourceRef.current) {
            activeEventSourceRef.current.close();
            activeEventSourceRef.current = null;
          }
          setWorkflowState('FAILED');
          setError('Reconciliation stream connection closed unexpectedly.');
        };
      }
    } catch (err) {
      if (activeEventSourceRef.current) {
        activeEventSourceRef.current.close();
        activeEventSourceRef.current = null;
      }
      setWorkflowState('FAILED');
      setError(err.message || 'Failed to start reconciliation.');
    }
  };

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
          triggerDemoRun();
        }
      } else {
        triggerDemoRun();
      }
    } catch (err) {
      triggerDemoRun();
    } finally {
      setLoading(false);
    }
  };

  const triggerDemoRun = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'demo' }),
      });
      if (res.ok) {
        const data = await res.json();
        setRuns([data]);
        setActiveRunId(data.run_id);
      }
    } catch (err) {
      setError('Failed to initialize demo run.');
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
      setError(`Failed to fetch details for run ${runId}`);
    }
  };

  const fetchTransactionDetail = async (txnId) => {
    if (!activeRunId) return;
    try {
      const res = await fetch(`/api/runs/${activeRunId}/transactions/${txnId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedTxnDetail(data);
      }
    } catch (err) {
      console.error(`Failed to fetch details for transaction ${txnId}`, err);
    }
  };

  const datasetSourceLabel = files.payments && files.ledger && files.bank ? 'Uploaded Custom CSVs' : 'Standard Benchmark Dataset';

  return (
    <div className="min-h-screen bg-slate-100 flex text-slate-800 antialiased font-sans">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        isOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 transition-all duration-200">
        <Header
          onRunReconciliation={handleRunReconciliation}
          workflowState={workflowState}
          datasetSource={datasetSourceLabel}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        />

        <main className="flex-1 p-4 sm:p-6 space-y-6 overflow-y-auto">
          {notification && (
            <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-mono p-3.5 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
                <span>{notification}</span>
              </div>
              <button
                onClick={() => setNotification(null)}
                className="text-emerald-700 hover:text-emerald-900 font-bold cursor-pointer"
              >
                ×
              </button>
            </div>
          )}

          {error && (
            <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs font-mono p-3.5 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-rose-600 flex-shrink-0" />
                <span>{error}</span>
              </div>
              <button
                onClick={() => setError(null)}
                className="text-rose-700 hover:text-rose-900 font-bold cursor-pointer"
              >
                ×
              </button>
            </div>
          )}

          {activeTab === 'dashboard' && (
            <>
              {/* 1. UPLOAD & VALIDATE DATA SOURCES */}
              <DataSourcesSection
                files={files}
                setFiles={setFiles}
                onRunReconciliation={handleRunReconciliation}
                workflowState={workflowState}
              />

              {/* 2. PROGRESSIVE EXECUTION & COMPACT RESULTS TRACKER */}
              <EvaluationPanel
                metrics={metrics}
                streamingState={streamingState}
                workflowState={workflowState}
                onRetry={handleRunReconciliation}
              />

              {/* 3. TOP SUMMARY KPI CARDS */}
              <KPICards metrics={metrics} />

              {/* 4. AI RESOLUTION BREAKDOWN */}
              <ResolutionBars metrics={metrics} />

              {/* 5. EXCEPTION DISTRIBUTION CHART */}
              <ExceptionChart metrics={metrics} />

              {/* 6. MAIN RECONCILIATION OPERATIONAL LEDGER TABLE */}
              <ReconciliationTable
                transactions={transactions}
                exceptions={exceptions}
                onSelectTransaction={fetchTransactionDetail}
              />

              {/* 7. ESCALATED EXCEPTIONS FOR HUMAN REVIEW */}
              <HumanReviewSection
                exceptions={exceptions}
                onSelectTransaction={fetchTransactionDetail}
              />
            </>
          )}

          {activeTab === 'runs' && (
            <RunsView
              runs={runs}
              activeRunId={activeRunId}
              onSelectRun={setActiveRunId}
              onTriggerRun={handleRunReconciliation}
              metrics={metrics}
              isRunning={workflowState === 'RUNNING_PHASE_1' || workflowState === 'RUNNING_AI'}
            />
          )}

          {activeTab === 'exceptions' && (
            <ExceptionsView
              exceptions={exceptions}
              onSelectTransaction={fetchTransactionDetail}
            />
          )}

          {activeTab === 'audit' && (
            <AuditLogView runId={activeRunId} />
          )}

          {activeTab === 'settings' && (
            <SettingsView
              settings={settings}
              onUpdateSettings={setSettings}
              metrics={metrics}
            />
          )}
        </main>
      </div>

      {/* Transaction Inspection Modal */}
      {selectedTxnDetail && (
        <ExceptionDetailModal
          detail={selectedTxnDetail}
          onClose={() => setSelectedTxnDetail(null)}
        />
      )}
    </div>
  );
}
