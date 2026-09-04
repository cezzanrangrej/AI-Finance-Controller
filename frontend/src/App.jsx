import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import KPICards from './components/KPICards';
import ResolutionBars from './components/ResolutionBars';
import ExceptionChart from './components/ExceptionChart';
import ReconciliationTable from './components/ReconciliationTable';
import HumanReviewSection from './components/HumanReviewSection';
import EvaluationPanel from './components/EvaluationPanel';
import DataSourcesSection from './components/DataSourcesSection';
import RunProgressPanel from './components/RunProgressPanel';
import ExceptionDetailModal from './components/ExceptionDetailModal';

import RunsView from './views/RunsView';
import ExceptionsView from './views/ExceptionsView';
import AuditLogView from './views/AuditLogView';
import SettingsView from './views/SettingsView';

import { useActiveRun } from './hooks/useActiveRun';
import { useReconciliationRun } from './hooks/useReconciliationRun';

import { CheckCircle2, AlertCircle } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Advanced developer settings.
  // Empty provider = inherit the backend's configured LLM_PROVIDER / role overrides.
  const [settings, setSettings] = useState({
    provider: '',
    batchSize: 5,
  });

  // User upload CSV files state
  const [files, setFiles] = useState({
    payments: null,
    ledger: null,
    bank: null,
    adjustments: null,
    // Optional scoring key, not a data source. Supplied, the run reports
    // measured accuracy; omitted, the accuracy fields come back as N/A.
    groundTruth: null,
  });

  // Custom Hook: Single source of truth for active run data
  const {
    activeRunId,
    setActiveRunId,
    runs,
    metrics,
    transactions,
    exceptions,
    selectedTxnDetail,
    setSelectedTxnDetail,
    inspectTransaction,
    refreshRuns,
    error: activeRunError,
    setError: setActiveRunError,
  } = useActiveRun();

  // Custom Hook: Handles reconciliation execution workflow state & SSE streaming
  const {
    workflowState,
    progressState,
    notification,
    setNotification,
    error: runError,
    setError: setRunError,
    runReconciliation,
  } = useReconciliationRun(setActiveRunId, refreshRuns);

  const handleRunReconciliation = () => {
    runReconciliation(files, settings, setActiveTab);
  };

  const datasetSourceLabel =
    files.payments && files.ledger && files.bank
      ? files.payments.name
        ? `${files.payments.name}, ${files.ledger.name}, ${files.bank.name}`
        : 'Uploaded Custom CSVs'
      : null;

  const displayedError = runError || activeRunError;

  return (
    <div className="min-h-screen bg-surface-alt flex text-text antialiased font-sans">
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
          activeRunId={activeRunId}
          onRunReconciliation={handleRunReconciliation}
          workflowState={workflowState}
          progressState={progressState}
          datasetSource={datasetSourceLabel}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        />

        <main className="flex-1 p-4 sm:p-6 space-y-6 overflow-y-auto">
          {notification && (
            <div className="bg-accent-green/10 border border-accent-green/30 text-text text-xs font-mono p-3.5 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-text flex-shrink-0" />
                <span>{notification}</span>
              </div>
              <button
                onClick={() => setNotification(null)}
                className="text-text-secondary hover:text-text font-bold cursor-pointer"
              >
                ×
              </button>
            </div>
          )}

          {displayedError && (
            <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs font-mono p-3.5 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-rose-600 flex-shrink-0" />
                <span>{displayedError}</span>
              </div>
              <button
                onClick={() => {
                  setRunError(null);
                  setActiveRunError(null);
                }}
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

              {/* 2. REAL-TIME RECONCILIATION PROGRESS PANEL */}
              <RunProgressPanel progressState={progressState} />

              {/* 2. PROGRESSIVE EXECUTION & COMPACT RESULTS TRACKER */}
              <EvaluationPanel
                metrics={metrics}
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
                onSelectTransaction={inspectTransaction}
              />

              {/* 7. ESCALATED EXCEPTIONS FOR HUMAN REVIEW */}
              <HumanReviewSection
                exceptions={exceptions}
                onSelectTransaction={inspectTransaction}
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
              isRunning={
                workflowState === 'RUNNING_PHASE_1' ||
                workflowState === 'RUNNING_AI' ||
                workflowState === 'VALIDATING' ||
                workflowState === 'UPLOADING'
              }
            />
          )}

          {activeTab === 'exceptions' && (
            <ExceptionsView
              exceptions={exceptions}
              onSelectTransaction={inspectTransaction}
            />
          )}

          {activeTab === 'audit' && (
            <AuditLogView
              activeRunId={activeRunId}
              onSelectTransaction={inspectTransaction}
            />
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
