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

  // Active SSE EventSource reference to guarantee 1 stream connection per run
  const activeEventSourceRef = useRef(null);

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
        } catch (_) {}
      });

      es.addEventListener('phase2_started', (e) => {
        try {
          const data = JSON.parse(e.data);
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
        } catch (_) {}
      });

      es.addEventListener('phase2_batch_progress', (e) => {
        try {
          const data = JSON.parse(e.data);
          setProgressState((prev) => ({
            ...prev,
            stage: 'PHASE_2',
            phase2: {
              batchesTotal: data.batch_total,
              batchesDone: data.batch_index,
              resolved: data.cumulative_resolved,
              humanReview: data.cumulative_human_review,
              exceptionCount: prev.phase2?.exceptionCount || 0,
            },
          }));
        } catch (_) {}
      });

      es.addEventListener('run_completed', async (e) => {
        try {
          const data = JSON.parse(e.data);
          es.close();
          activeEventSourceRef.current = null;

          setProgressState((prev) => ({
            ...prev,
            stage: 'COMPLETED',
          }));
          setWorkflowState('COMPLETED');
          setNotification(`Reconciliation completed successfully for uploaded dataset (Run ${data.run_id || run_id}).`);

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

          setProgressState((prev) => ({
            ...prev,
            stage: 'FAILED',
            error: data.error,
          }));
          setWorkflowState('FAILED');
          setError(data.error || 'Reconciliation failed.');
        } catch (_) {}
      });

      es.onerror = () => {
        // SSE error or closure
        if (es.readyState === EventSource.CLOSED) {
          activeEventSourceRef.current = null;
        }
      };
    } catch (err) {
      if (activeEventSourceRef.current) {
        activeEventSourceRef.current.close();
        activeEventSourceRef.current = null;
      }
      setProgressState((prev) => ({ ...prev, stage: 'FAILED', error: err.message }));
      setWorkflowState('FAILED');
      setError(err.message || 'Failed to start reconciliation.');
    }
  };

  return {
    workflowState,
    progressState,
    notification,
    setNotification,
    error,
    setError,
    runReconciliation,
  };
}
