import { useState, useRef, useEffect } from 'react';
import { startUploadReconciliation } from '../lib/api';

export function useReconciliationRun(setActiveRunId, refreshRuns) {
  const [workflowState, setWorkflowState] = useState('READY');
  const [notification, setNotification] = useState(null);
  const [error, setError] = useState(null);
  const [progressState, setProgressState] = useState({
    stage: 'READY', // 'READY' | 'UPLOADING' | 'PHASE_1' | 'PHASE_2' | 'COMPLETED' | 'FAILED'
    totalRecords: 0,
    phase1: null, // { reconciled: 0, exceptions: 0, total: 0 }
    phase2: null, // { batchesTotal: 0, batchesDone: 0, resolved: 0, humanReview: 0, exceptionCount: 0 }
    error: null,
  });

  const [streamingState, setStreamingState] = useState({
    isStreaming: false,
    totalCases: 0,
    casesCompleted: 0,
    totalBatches: 0,
    batches: {},
    totalRecords: 0,
    initialReconciled: 0,
    initialExceptions: 0,
    error: null,
  });

  // Active SSE EventSource reference to guarantee 1 stream connection per run
  const activeEventSourceRef = useRef(null);
  // True once a terminal event (run_completed / run_error) has been handled, so
  // a late onerror from the closing stream cannot overwrite the final state.
  const runSettledRef = useRef(false);

  useEffect(() => {
    return () => {
      if (activeEventSourceRef.current) {
        activeEventSourceRef.current.close();
        activeEventSourceRef.current = null;
      }
    };
  }, []);

  const runReconciliation = async (files, settings, onTabChange) => {
    // 1. Idempotency Guard: prevent duplicate submissions while run is active
    if (
      workflowState === 'RUNNING_PHASE_1' ||
      workflowState === 'RUNNING_AI' ||
      workflowState === 'VALIDATING' ||
      workflowState === 'UPLOADING'
    ) {
      console.warn('[FRONTEND GUARD] Reconciliation already in progress. Ignoring duplicate submission.');
      return;
    }

    try {
      setError(null);
      setNotification(null);
      runSettledRef.current = false;

      if (activeEventSourceRef.current) {
        activeEventSourceRef.current.close();
        activeEventSourceRef.current = null;
      }

      const hasCustomFiles = Boolean(files.payments && files.ledger && files.bank);
      if (!hasCustomFiles) {
        setError('Please upload Payments, Ledger, and Bank CSV files in Data Sources before running reconciliation.');
        if (onTabChange) onTabChange('datasources');
        return;
      }

      setWorkflowState('UPLOADING');
      setProgressState({
        stage: 'UPLOADING',
        totalRecords: 0,
        phase1: null,
        phase2: null,
        error: null,
      });
      setStreamingState({
        isStreaming: false,
        totalCases: 0,
        casesCompleted: 0,
        totalBatches: 0,
        batches: {},
        totalRecords: 0,
        initialReconciled: 0,
        initialExceptions: 0,
        error: null,
      });

      const formData = new FormData();
      formData.append('payments', files.payments);
      formData.append('ledger', files.ledger);
      formData.append('bank', files.bank);
      if (files.adjustments) formData.append('adjustments', files.adjustments);
      if (settings?.provider) formData.append('provider', settings.provider);
      if (settings?.batchSize) formData.append('batch_size', String(settings.batchSize));

      const { run_id, stream_url } = await startUploadReconciliation(formData);

      setWorkflowState('RUNNING_PHASE_1');
      setProgressState((prev) => ({ ...prev, stage: 'PHASE_1' }));

      // Open SSE Stream connection
      const es = new EventSource(stream_url);
      activeEventSourceRef.current = es;

      es.addEventListener('phase1_started', (e) => {
        try {
          const data = JSON.parse(e.data);
          setProgressState((prev) => ({
            ...prev,
            stage: 'PHASE_1',
            totalRecords: data.total_records || 0,
          }));
          setWorkflowState('RUNNING_PHASE_1');
        } catch (_) {}
      });

      es.addEventListener('phase1_completed', (e) => {
        try {
          const data = JSON.parse(e.data);
          setProgressState((prev) => ({
            ...prev,
            stage: 'PHASE_1',
            totalRecords: data.total || prev.totalRecords,
            phase1: {
              reconciled: data.reconciled,
              exceptions: data.exceptions,
              total: data.total,
            },
          }));
          setStreamingState((prev) => ({
            ...prev,
            totalRecords: data.total || prev.totalRecords,
            initialReconciled: data.reconciled ?? 0,
            initialExceptions: data.exceptions ?? 0,
          }));
        } catch (_) {}
      });

      es.addEventListener('phase2_started', (e) => {
        try {
          const data = JSON.parse(e.data);
          const batchesMap = {};
          if (Array.isArray(data.batch_details)) {
            data.batch_details.forEach((b) => {
              batchesMap[b.batch_number] = {
                batchNumber: b.batch_number,
                status: 'PENDING',
                caseCount: b.case_count,
              };
            });
          } else {
            for (let i = 1; i <= (data.batch_count || 0); i++) {
              batchesMap[i] = {
                batchNumber: i,
                status: 'PENDING',
                caseCount: data.batch_size || 5,
              };
            }
          }

          setProgressState((prev) => ({
            ...prev,
            stage: 'PHASE_2',
            phase2: {
              batchesTotal: data.batch_count,
              batchesDone: 0,
              resolved: 0,
              humanReview: 0,
              exceptionCount: data.exception_count,
            },
          }));
          setWorkflowState('RUNNING_AI');
          setStreamingState((prev) => ({
            ...prev,
            isStreaming: true,
            totalCases: data.exception_count,
            casesCompleted: 0,
            totalBatches: data.batch_count,
            batches: batchesMap,
          }));
        } catch (_) {}
      });

      es.addEventListener('phase2_batch_started', (e) => {
        try {
          const data = JSON.parse(e.data);
          const bNum = data.batch_index;
          setStreamingState((prev) => {
            const currentBatches = prev.batches ? { ...prev.batches } : {};
            currentBatches[bNum] = {
              ...(currentBatches[bNum] || { batchNumber: bNum }),
              batchNumber: bNum,
              status: 'RUNNING',
              caseCount: data.cases_in_batch ?? currentBatches[bNum]?.caseCount ?? 5,
            };
            return {
              ...prev,
              batches: currentBatches,
            };
          });
        } catch (_) {}
      });

      es.addEventListener('phase2_batch_progress', (e) => {
        try {
          const data = JSON.parse(e.data);
          const bNum = data.batch_index;
          setProgressState((prev) => ({
            ...prev,
            stage: 'PHASE_2',
            phase2: {
              batchesTotal: data.batch_total,
              batchesDone: data.completed_batches ?? data.batch_index,
              resolved: data.cumulative_resolved,
              humanReview: data.cumulative_human_review,
              // Cases the LLM never actually judged (provider/parse failure).
              // Dropping this made a batch that failed outright indistinguishable
              // from one that legitimately escalated nothing.
              notEvaluated: data.cumulative_not_evaluated ?? 0,
              exceptionCount: prev.phase2?.exceptionCount || 0,
            },
          }));
          setStreamingState((prev) => {
            const currentBatches = prev.batches ? { ...prev.batches } : {};
            currentBatches[bNum] = {
              ...(currentBatches[bNum] || { batchNumber: bNum }),
              batchNumber: bNum,
              status: 'COMPLETED',
              caseCount: data.cases_in_batch ?? currentBatches[bNum]?.caseCount ?? 5,
              durationSec: data.batch_time_sec,
            };
            const completedCases = Object.values(currentBatches)
              .filter((b) => b.status === 'COMPLETED')
              .reduce((sum, b) => sum + (b.caseCount || 0), 0);

            return {
              ...prev,
              casesCompleted: completedCases,
              batches: currentBatches,
            };
          });
        } catch (_) {}
      });

      es.addEventListener('rate_limited_retry', (e) => {
        try {
          const data = JSON.parse(e.data);
          const bNum = data.batch_index;
          setStreamingState((prev) => {
            const currentBatches = prev.batches ? { ...prev.batches } : {};
            currentBatches[bNum] = {
              ...(currentBatches[bNum] || { batchNumber: bNum }),
              batchNumber: bNum,
              status: 'RETRYING',
              caseCount: currentBatches[bNum]?.caseCount ?? 5,
              retryInfo: `Retry ${data.attempt}/${data.max_attempts} (${data.wait_seconds}s)`,
            };
            return {
              ...prev,
              batches: currentBatches,
            };
          });
        } catch (_) {}
      });

      es.addEventListener('run_completed', async (e) => {
        try {
          const data = JSON.parse(e.data);
          es.close();
          activeEventSourceRef.current = null;
          runSettledRef.current = true;

          const notEvaluated = data.not_evaluated ?? 0;
          const degradedCases = data.degraded_cases ?? 0;
          // True when the Phase-2 verdicts came from the offline rule emulator
          // rather than a real model — either because demo was selected or
          // because a configured provider silently fell back to it.
          const isEmulated =
            Boolean(data.llm_degraded) ||
            String(data.llm_mode || '').toUpperCase() === 'DEMO' ||
            String(data.llm_provider || '').toLowerCase() === 'demo';

          setProgressState((prev) => ({
            ...prev,
            stage: 'COMPLETED',
            notEvaluated,
            degradedCases,
            isEmulated,
            hasGroundTruth: Boolean(data.has_ground_truth),
          }));
          setWorkflowState('COMPLETED');

          // A run where no case was evaluated completed as a pipeline but
          // produced no AI findings; reporting that as an unqualified success
          // is the misleading outcome this project explicitly guards against.
          // degraded_cases is a batch-level count of the same failures that
          // not_evaluated counts per decision, so only the latter is reported —
          // listing both read as twice as many broken cases as there were.
          const runLabel = data.run_id || run_id;
          const parts = [];
          if (notEvaluated > 0) parts.push(`${notEvaluated} case(s) were not evaluated`);
          if (isEmulated) {
            parts.push(
              data.llm_degraded
                ? `the AI step fell back to the offline emulator (${data.llm_degraded_reason || 'provider unavailable'})`
                : 'the AI step ran on the offline demo emulator, not a real model'
            );
          }
          if (parts.length > 0) {
            setNotification(
              `Reconciliation finished for Run ${runLabel}, but ${parts.join(' and ')}. Review before relying on these results.`
            );
          } else {
            setNotification(`Reconciliation completed successfully for uploaded dataset (Run ${runLabel}).`);
          }

          setStreamingState((prev) => ({
            ...prev,
            isStreaming: false,
            casesCompleted: prev.totalCases || prev.casesCompleted,
          }));

          if (setActiveRunId) {
            setActiveRunId(data.run_id || run_id);
          }
          if (refreshRuns) {
            await refreshRuns(data.run_id || run_id);
          }
        } catch (_) {}
      });

      es.addEventListener('run_error', (e) => {
        try {
          const data = JSON.parse(e.data);
          es.close();
          activeEventSourceRef.current = null;
          runSettledRef.current = true;

          setProgressState((prev) => ({
            ...prev,
            stage: 'FAILED',
            error: data.error,
          }));
          setStreamingState((prev) => ({
            ...prev,
            isStreaming: false,
            error: data.error,
          }));
          setWorkflowState('FAILED');
          setError(data.error || 'Reconciliation failed.');
        } catch (_) {}
      });

      es.onerror = () => {
        // A dropped connection previously left the UI pinned to RUNNING_AI
        // forever, because only run_error/run_completed could move it off.
        // EventSource retries automatically while CONNECTING; only a CLOSED
        // stream that never delivered a terminal event is a real failure.
        if (es.readyState !== EventSource.CLOSED) return;

        activeEventSourceRef.current = null;
        if (runSettledRef.current) return;
        runSettledRef.current = true;

        setProgressState((prev) => ({
          ...prev,
          stage: 'FAILED',
          error: 'Lost connection to the reconciliation stream.',
        }));
        setStreamingState((prev) => ({
          ...prev,
          isStreaming: false,
          error: 'Lost connection to the reconciliation stream.',
        }));
        setWorkflowState('FAILED');
        setError(
          `Lost connection to the reconciliation stream before it finished. The run may still be executing on the server — check the Runs tab for ${run_id}.`
        );
      };
    } catch (err) {
      if (activeEventSourceRef.current) {
        activeEventSourceRef.current.close();
        activeEventSourceRef.current = null;
      }
      setProgressState((prev) => ({ ...prev, stage: 'FAILED', error: err.message }));
      setStreamingState((prev) => ({ ...prev, isStreaming: false, error: err.message }));
      setWorkflowState('FAILED');
      setError(err.message || 'Failed to start reconciliation.');
    }
  };

  return {
    workflowState,
    progressState,
    streamingState,
    notification,
    setNotification,
    error,
    setError,
    runReconciliation,
  };
}
