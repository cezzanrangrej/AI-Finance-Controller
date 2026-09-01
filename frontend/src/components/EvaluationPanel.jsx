import React from 'react';
import { Target, CheckCircle2, Cpu, Zap, Activity, Clock, Loader2, AlertCircle, RefreshCw, ShieldCheck } from 'lucide-react';

export default function EvaluationPanel({
  metrics,
  streamingState,
  workflowState,
  onRetry,
}) {
  const isUploading = workflowState === 'UPLOADING';
  const isValidating = workflowState === 'VALIDATING';
  const isStarting = workflowState === 'STARTING_RECONCILIATION';
  const isRunningPhase1 = workflowState === 'RUNNING_PHASE_1';
  const isRunningAI = workflowState === 'RUNNING_AI';
  const isCompleted = workflowState === 'COMPLETED';
  const isFailed = workflowState === 'FAILED';

  const totalRecords = metrics?.total_records ?? 0;
  const initialReconciled = metrics?.initial_reconciled ?? 0;
  const initialExceptions = metrics?.initial_exceptions ?? (totalRecords >= initialReconciled ? totalRecords - initialReconciled : 0);
  const aiAutoResolved = metrics?.ai_auto_resolved ?? metrics?.ai_resolved ?? 0;
  const humanReview = metrics?.human_review ?? (initialExceptions >= aiAutoResolved ? initialExceptions - aiAutoResolved : 0);

  const initialMatchRate = metrics?.initial_match_rate ?? (totalRecords > 0 ? (initialReconciled / totalRecords) * 100 : 0);
  const finalResolutionRate = metrics?.final_resolution_rate ?? (totalRecords > 0 ? ((initialReconciled + aiAutoResolved) / totalRecords) * 100 : 0);
  const aiResolutionRate = metrics?.agent_resolution_rate ?? metrics?.ai_resolution_rate ?? (initialExceptions > 0 ? (aiAutoResolved / initialExceptions) * 100 : 0);

  const hasGroundTruth = Boolean(metrics?.has_ground_truth || metrics?.ground_truth_accuracy != null || metrics?.phase2_accuracy != null);
  const phase2Accuracy = metrics?.phase2_accuracy ?? metrics?.ground_truth_accuracy;
  const precision = metrics?.auto_resolution_precision;
  const recall = metrics?.auto_resolution_recall;

  const batchList = streamingState?.batches ? Object.values(streamingState.batches) : [];

  return (
    <div className="bg-background border border-border rounded-lg p-6 space-y-6 shadow-xs">
      
      {/* 1. UPLOADING STATE */}
      {isUploading && (
        <div className="bg-primary/10 border border-primary/30 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Loader2 className="h-5 w-5 text-primary animate-spin" />
              <div>
                <h3 className="text-sm font-bold text-text uppercase tracking-wide">
                  Uploading Source Datasets
                </h3>
                <p className="text-xs text-text-secondary font-mono">
                  Streaming source CSV files to server...
                </p>
              </div>
            </div>
            <span className="text-[10px] font-mono font-semibold px-2.5 py-1 rounded bg-primary/15 text-primary border border-primary/30">
              Uploading
            </span>
          </div>
        </div>
      )}

      {/* 2. VALIDATING STATE */}
      {isValidating && (
        <div className="bg-accent-purple/10 border border-accent-purple/30 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Loader2 className="h-5 w-5 text-accent-purple animate-spin" />
              <div>
                <h3 className="text-sm font-bold text-text uppercase tracking-wide">
                  Validating Invariants
                </h3>
                <p className="text-xs text-text-secondary font-mono">
                  Checking schema columns and Decimal precision invariants...
                </p>
              </div>
            </div>
            <span className="text-[10px] font-mono font-semibold px-2.5 py-1 rounded bg-accent-purple/15 text-accent-purple border border-accent-purple/30">
              Validating
            </span>
          </div>
        </div>
      )}

      {/* 3. STARTING_RECONCILIATION STATE */}
      {isStarting && (
        <div className="bg-accent-coral/10 border border-accent-coral/30 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Loader2 className="h-5 w-5 text-accent-coral animate-spin" />
              <div>
                <h3 className="text-sm font-bold text-text uppercase tracking-wide">
                  Starting Reconciliation
                </h3>
                <p className="text-xs text-text-secondary font-mono">
                  Initializing reconciliation pipeline and worker threads...
                </p>
              </div>
            </div>
            <span className="text-[10px] font-mono font-semibold px-2.5 py-1 rounded bg-accent-coral/15 text-accent-coral border border-accent-coral/30">
              Initializing
            </span>
          </div>
        </div>
      )}

      {/* 4. RUNNING_PHASE_1 STATE */}
      {isRunningPhase1 && (
        <div className="bg-accent-coral/10 border border-accent-coral/30 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Loader2 className="h-5 w-5 text-accent-coral animate-spin" />
              <div>
                <h3 className="text-sm font-bold text-text uppercase tracking-wide">
                  Phase 1 Execution
                </h3>
                <p className="text-xs text-text-secondary font-mono">
                  Phase 1: Deterministic Double-Entry Engine reconciling 4-source records...
                </p>
              </div>
            </div>
            <span className="text-[10px] font-mono font-semibold px-2.5 py-1 rounded bg-accent-coral/15 text-accent-coral border border-accent-coral/30">
              Phase 1 Engine
            </span>
          </div>

          <div className="w-full bg-accent-coral/20 h-2 rounded-full overflow-hidden">
            <div className="bg-accent-coral h-full w-1/3 animate-pulse rounded-full" />
          </div>
        </div>
      )}

      {/* 2. RUNNING_AI STATE (Progressive SSE Execution & Compact Batch Tracker) */}
      {(isRunningAI || (streamingState && streamingState.isStreaming)) && (
        <div className="bg-surface border border-border rounded-lg p-5 space-y-4">
          
          {/* Phase 1 Complete Summary Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-text" />
              <span className="text-xs font-semibold uppercase tracking-wider text-text">
                Phase 1 Complete
              </span>
              <span className="text-xs font-mono text-text-secondary">
                ({totalRecords} records processed · {initialReconciled} reconciled · <strong>{initialExceptions} exceptions detected</strong>)
              </span>
            </div>

            <span className="text-[10px] font-mono px-2.5 py-0.5 rounded bg-accent-green/10 text-text border border-accent-green/30 font-semibold self-start sm:self-auto">
              Auto-Queued {streamingState?.totalCases || initialExceptions} Cases
            </span>
          </div>

          {/* AI Investigation Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 text-accent-purple animate-spin" />
              <span className="text-xs font-bold text-text uppercase tracking-wider">
                AI Parallel Investigation
              </span>
              <span className="text-xs font-mono text-text-secondary/60">
                ({streamingState?.totalBatches || 3} batches running in parallel)
              </span>
            </div>

            <div className="text-xs font-mono text-text-secondary">
              <strong>{streamingState?.casesCompleted || 0}</strong> / {streamingState?.totalCases || initialExceptions} cases completed
            </div>
          </div>

          {/* Compact Progress Bar */}
          <div className="w-full bg-border h-2.5 rounded-full overflow-hidden">
            <div
              className="bg-primary h-full transition-all duration-300 rounded-full"
              style={{
                width: `${streamingState?.totalCases ? Math.min(100, ((streamingState.casesCompleted || 0) / streamingState.totalCases) * 100) : 0}%`,
              }}
            />
          </div>

          {/* Compact Batch Status Chips */}
          {batchList.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pt-1 font-mono text-xs">
              {batchList.map((b) => (
                <div
                  key={b.batchNumber}
                  className={`px-3 py-1.5 rounded-md border flex items-center gap-2 transition-all ${
                    b.status === 'COMPLETED'
                      ? 'bg-accent-green/10 border-accent-green/30 text-text'
                      : b.status === 'RUNNING'
                      ? 'bg-accent-coral/10 border-accent-coral/30 text-text animate-pulse'
                      : 'bg-background border-border text-text-secondary'
                  }`}
                >
                  {b.status === 'COMPLETED' ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-text flex-shrink-0" />
                  ) : b.status === 'RUNNING' ? (
                    <Loader2 className="h-3.5 w-3.5 text-accent-coral animate-spin flex-shrink-0" />
                  ) : (
                    <span className="h-2 w-2 rounded-full bg-border" />
                  )}
                  <span className="font-semibold">Batch #{b.batchNumber}</span>
                  <span className="text-[11px] text-text-secondary/60">({b.caseCount} cases)</span>
                  {b.durationSec && <span className="text-[10px] text-text font-bold">{b.durationSec.toFixed(2)}s</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3. FAILED STATE */}
      {isFailed && (
        <div className="bg-rose-50 border border-rose-200 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-rose-800 font-bold text-sm">
              <AlertCircle className="h-5 w-5 text-rose-600 flex-shrink-0" />
              <span>Reconciliation Failed</span>
            </div>
            <button
              onClick={onRetry}
              className="px-3.5 py-1.5 bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold rounded-md shadow-xs transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Retry</span>
            </button>
          </div>
          <p className="text-xs text-rose-700 font-mono">
            {metrics?.error || streamingState?.error || 'An unexpected error occurred during parallel investigation.'}
          </p>
        </div>
      )}

      {/* 4. FINAL COMPLETED RESULTS & METRICS SUMMARY */}
      {(isCompleted || (!isRunningPhase1 && !isRunningAI && metrics)) && (
        <div className="space-y-6">
          
          {/* Completion Banner */}
          <div className="bg-accent-green/10 border border-accent-green/30 rounded-lg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-text" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-text">
                  Reconciliation Complete
                </h3>
              </div>
              <p className="text-xs text-text-secondary font-mono mt-1">
                <strong>{totalRecords}</strong> records processed · <strong>{initialReconciled}</strong> initial match · <strong>{initialExceptions}</strong> exceptions investigated
              </p>
            </div>

            <div className="flex items-center gap-3 text-xs font-mono">
              <div className="bg-background px-3 py-1.5 rounded border border-accent-green/30 text-text">
                AI Auto-Resolved: <strong>{aiAutoResolved}</strong>
              </div>
              <div className="bg-background px-3 py-1.5 rounded border border-accent-coral/30 text-text">
                Human Review: <strong>{humanReview}</strong>
              </div>
            </div>
          </div>

          {/* Operational Metrics Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-surface border border-border rounded-lg p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary block mb-1">
                Initial Match Rate
              </span>
              <div className="text-2xl font-bold font-mono text-text">
                {initialMatchRate.toFixed(1)}%
              </div>
              <p className="text-[11px] text-text-secondary mt-1">Phase 1 double-entry match rate.</p>
            </div>

            <div className="bg-surface border border-border rounded-lg p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary block mb-1">
                Final Resolution Rate
              </span>
              <div className="text-2xl font-bold font-mono text-primary">
                {finalResolutionRate.toFixed(1)}%
              </div>
              <p className="text-[11px] text-text-secondary mt-1">Total resolved (Phase 1 + AI auto-resolved).</p>
            </div>

            <div className="bg-surface border border-border rounded-lg p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary block mb-1">
                AI Exception Resolution
              </span>
              <div className="text-2xl font-bold font-mono text-primary">
                {aiResolutionRate.toFixed(1)}%
              </div>
              <p className="text-[11px] text-text-secondary mt-1">Exceptions resolved with financial proof.</p>
            </div>
          </div>

          {/* Ground Truth Benchmark Metrics (ONLY DISPLAYED IF GROUND TRUTH EXISTS) */}
          {hasGroundTruth && (
            <div className="bg-surface border border-border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-border pb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-text">
                  Ground Truth Benchmark Accuracy
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent-green/10 text-text border border-accent-green/30 font-medium">
                  Verified Ground Truth
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                <div className="bg-background p-3 rounded border border-border">
                  <span className="text-[10px] text-text-secondary/60 block font-sans">Decision Accuracy</span>
                  <span className="text-lg font-bold text-text">
                    {phase2Accuracy != null ? `${Number(phase2Accuracy).toFixed(1)}%` : '—'}
                  </span>
                </div>
                <div className="bg-background p-3 rounded border border-border">
                  <span className="text-[10px] text-text-secondary/60 block font-sans">Precision (Zero False Positives)</span>
                  <span className="text-lg font-bold text-primary">
                    {precision != null ? `${Number(precision).toFixed(1)}%` : '—'}
                  </span>
                </div>
                <div className="bg-background p-3 rounded border border-border">
                  <span className="text-[10px] text-text-secondary/60 block font-sans">Recall (Explainable Recovery)</span>
                  <span className="text-lg font-bold text-primary">
                    {recall != null ? `${Number(recall).toFixed(1)}%` : '—'}
                  </span>
                </div>
              </div>
            </div>
          )}

        </div>
      )}

    </div>
  );
}
