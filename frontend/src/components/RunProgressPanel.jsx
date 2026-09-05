import React from 'react';
import { CheckCircle2, Loader2, AlertCircle, Circle } from 'lucide-react';

export default function RunProgressPanel({ progressState, metrics }) {
  if (!progressState || progressState.stage === 'READY') {
    return null;
  }

  const {
    stage,
    totalRecords,
    phase1,
    preBatch,
    phase2,
    error,
    notEvaluated,
    isEmulated,
    preResolvedCount,
    llmCasesSelected,
  } = progressState;

  const isUploading = stage === 'UPLOADING';
  const isPhase1 = stage === 'PHASE_1';
  const isPreBatch = stage === 'PRE_BATCH';
  const isPhase2 = stage === 'PHASE_2';
  const isCompleted = stage === 'COMPLETED';
  const isFailed = stage === 'FAILED';

  // Determine actual numbers for the Pre-Batch stage
  const preBatchInfo = preBatch || (
    preResolvedCount != null
      ? {
          preResolved: preResolvedCount,
          remaining: llmCasesSelected ?? Math.max(0, (phase1?.exceptions ?? 0) - preResolvedCount),
          total: phase1?.exceptions ?? 0,
        }
      : metrics?.pre_resolved_count != null
      ? {
          preResolved: metrics.pre_resolved_count,
          remaining: metrics.llm_cases_selected ?? Math.max(0, (metrics.initial_exceptions ?? 0) - metrics.pre_resolved_count),
          total: metrics.initial_exceptions ?? 0,
        }
      : (phase1 && (isPhase2 || isCompleted))
      ? {
          preResolved: Math.max(0, (phase1.exceptions || 0) - (phase2?.exceptionCount ?? 0)),
          remaining: phase2?.exceptionCount ?? 0,
          total: phase1.exceptions || 0,
        }
      : null
  );

  // A run that never got past ingestion previously still showed step 1 with a
  // green tick, so a parse failure rendered as a successfully ingested file.
  const step1Status = isUploading ? 'running' : isFailed && !phase1 ? 'failed' : 'done';
  // Step 2: Phase 1 Match
  const step2Status = isPhase1 ? 'running' : phase1 || isPreBatch || isPhase2 || isCompleted ? 'done' : 'pending';
  // Step 3: Pre-Batch Proof
  const step3Status = isPreBatch ? 'running' : (preBatchInfo || isPhase2 || isCompleted) ? 'done' : 'pending';
  // Step 4: Phase 2 AI Multi-Agent
  const step4Status = isPhase2 ? 'running' : isCompleted ? 'done' : 'pending';
  // Step 5: Final Resolution
  const step5Status = isCompleted ? 'done' : isFailed ? 'failed' : 'pending';

  // Integrity warning for un-evaluated or emulated runs
  const hasIntegrityWarning = isCompleted && ((notEvaluated || 0) > 0 || Boolean(isEmulated));

  const renderIcon = (status) => {
    switch (status) {
      case 'done':
        return <CheckCircle2 className="h-4 w-4 text-accent-green flex-shrink-0" />;
      case 'running':
        return <Loader2 className="h-4 w-4 text-primary animate-spin flex-shrink-0" />;
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-rose-600 flex-shrink-0" />;
      default:
        return <Circle className="h-3.5 w-3.5 text-text-secondary/40 flex-shrink-0" />;
    }
  };

  return (
    <div className="bg-background border border-border rounded-lg p-5 shadow-xs space-y-4 animate-in fade-in-50 duration-200">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text">
            Live Reconciliation Pipeline
          </h3>
        </div>
        <span className="text-[11px] font-mono text-text-secondary">
          {stage === 'COMPLETED' ? 'Run Finished' : stage === 'FAILED' ? 'Execution Error' : 'Processing Live'}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {/* Step 1: Data Ingestion */}
        <div className={`p-3 rounded-lg border text-xs transition-colors ${
          step1Status === 'running'
            ? 'bg-primary/5 border-primary/30 text-text'
            : 'bg-surface border-border text-text'
        }`}>
          <div className="flex items-center gap-2 font-semibold">
            {renderIcon(step1Status)}
            <span>1. Data Ingestion</span>
          </div>
          <p className="text-[11px] text-text-secondary mt-1 ml-6">
            {totalRecords > 0 ? `${totalRecords.toLocaleString()} records ingested` : 'Parsing CSV files...'}
          </p>
        </div>

        {/* Step 2: Phase 1 Deterministic Engine */}
        <div className={`p-3 rounded-lg border text-xs transition-colors ${
          step2Status === 'running'
            ? 'bg-primary/5 border-primary/30 text-text'
            : step2Status === 'done'
            ? 'bg-surface border-border text-text'
            : 'bg-surface-alt/50 border-border/60 text-text-secondary/60'
        }`}>
          <div className="flex items-center gap-2 font-semibold">
            {renderIcon(step2Status)}
            <span>2. Phase 1 Match</span>
          </div>
          <p className="text-[11px] text-text-secondary mt-1 ml-6">
            {phase1
              ? `${phase1.reconciled.toLocaleString()} matched, ${phase1.exceptions.toLocaleString()} exceptions`
              : step2Status === 'running'
              ? 'Multi-key hashing...'
              : 'Awaiting engine'}
          </p>
        </div>

        {/* Step 3: Pre-Batch Deterministic Proof */}
        <div className={`p-3 rounded-lg border text-xs transition-colors ${
          step3Status === 'running'
            ? 'bg-primary/5 border-primary/30 text-text'
            : step3Status === 'done'
            ? 'bg-surface border-border text-text'
            : 'bg-surface-alt/50 border-border/60 text-text-secondary/60'
        }`}>
          <div className="flex items-center gap-2 font-semibold">
            {renderIcon(step3Status)}
            <span>3. Pre-Batch Proof</span>
          </div>
          <p className="text-[11px] text-text-secondary mt-1 ml-6">
            {preBatchInfo
              ? (preBatchInfo.total === 0 || (phase1 && phase1.exceptions === 0))
                ? '0 exceptions flagged'
                : `${preBatchInfo.preResolved.toLocaleString()} pre-resolved, ${preBatchInfo.remaining.toLocaleString()} to AI`
              : step3Status === 'running'
              ? 'Evaluating Decimal proofs...'
              : 'Awaiting Phase 1'}
          </p>
        </div>

        {/* Step 4: Phase 2 AI Multi-Agent */}
        <div className={`p-3 rounded-lg border text-xs transition-colors ${
          step4Status === 'running'
            ? 'bg-primary/5 border-primary/30 text-text'
            : step4Status === 'done'
            ? 'bg-surface border-border text-text'
            : 'bg-surface-alt/50 border-border/60 text-text-secondary/60'
        }`}>
          <div className="flex items-center gap-2 font-semibold">
            {renderIcon(step4Status)}
            <span>4. AI Investigation</span>
          </div>
          <p className="text-[11px] text-text-secondary mt-1 ml-6">
            {phase2
              ? phase2.batchesTotal === 0
                ? '0 cases (all pre-resolved)'
                : `Batch ${phase2.batchesDone}/${phase2.batchesTotal} (${phase2.llmResolved ?? phase2.resolved} res, ${phase2.humanReview} esc${
                    phase2.notEvaluated ? `, ${phase2.notEvaluated} n/e` : ''
                  })`
              : step4Status === 'running'
              ? 'Prefetching evidence...'
              : 'Awaiting exceptions'}
          </p>
        </div>

        {/* Step 5: Final Resolution */}
        <div className={`p-3 rounded-lg border text-xs transition-colors ${
          hasIntegrityWarning
            ? 'bg-amber-50 border-amber-200 text-amber-900'
            : step5Status === 'done'
            ? 'bg-accent-green/10 border-accent-green/30 text-text'
            : step5Status === 'failed'
            ? 'bg-rose-50 border-rose-200 text-rose-800'
            : 'bg-surface-alt/50 border-border/60 text-text-secondary/60'
        }`}>
          <div className="flex items-center gap-2 font-semibold">
            {hasIntegrityWarning ? (
              <AlertCircle className="h-4 w-4 text-amber-600 flex-shrink-0" />
            ) : (
              renderIcon(step5Status)
            )}
            <span>5. Final Resolution</span>
          </div>
          <p className="text-[11px] mt-1 ml-6 text-current/80">
            {hasIntegrityWarning
              ? [
                  notEvaluated ? `${notEvaluated} not evaluated` : null,
                  isEmulated ? 'offline emulator, not a real model' : null,
                ]
                  .filter(Boolean)
                  .join(', ') + ' - verify before use'
              : isCompleted
              ? 'Saved to audit trail'
              : isFailed
              ? error || 'Pipeline failed'
              : 'Awaiting completion'}
          </p>
        </div>
      </div>
    </div>
  );
}
