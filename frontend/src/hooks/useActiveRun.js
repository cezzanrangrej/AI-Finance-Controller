import { useState, useEffect, useCallback } from 'react';
import {
  fetchRuns,
  fetchRunMetrics,
  fetchRunTransactions,
  fetchRunExceptions,
  fetchTransactionDetail,
} from '../lib/api';

export function useActiveRun() {
  const [activeRunId, setActiveRunId] = useState(null);
  const [runs, setRuns] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [selectedTxnDetail, setSelectedTxnDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch all runs and select target or first run
  const refreshRuns = useCallback(async (targetRunId = null) => {
    try {
      setLoading(true);
      const data = await fetchRuns();
      setRuns(data);
      if (targetRunId) {
        setActiveRunId(targetRunId);
      } else {
        // Never adopt a run the user did not ask for. Seeding this with the most
        // recent stored run made the dashboard open on some earlier dataset's
        // figures: the header truthfully read "No dataset loaded" while every KPI,
        // chart and ledger row below it described an unrelated previous run.
        // A run becomes active only when one finishes here (refreshRuns(runId))
        // or when the user selects one in the Runs tab. Keeping an already
        // selected run alive matters for the post-run refresh; if it has since
        // been deleted server-side, clearing it lets the derived-data effect
        // reset metrics/transactions/exceptions.
        setActiveRunId((prev) => (prev && data.some((r) => r.run_id === prev) ? prev : null));
      }
    } catch (err) {
      setRuns([]);
      setActiveRunId(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch runs on initial mount
  useEffect(() => {
    refreshRuns();
  }, [refreshRuns]);

  // Re-fetch metrics/transactions/exceptions whenever activeRunId changes
  useEffect(() => {
    if (!activeRunId) {
      setMetrics(null);
      setTransactions([]);
      setExceptions([]);
      return;
    }

    let isMounted = true;

    async function loadRunData() {
      try {
        const [m, t, e] = await Promise.all([
          fetchRunMetrics(activeRunId),
          fetchRunTransactions(activeRunId),
          fetchRunExceptions(activeRunId),
        ]);
        if (isMounted) {
          setMetrics(m);
          setTransactions(t);
          setExceptions(e);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message);
        }
      }
    }

    loadRunData();

    return () => {
      isMounted = false;
    };
  }, [activeRunId]);

  // Inspect specific transaction detail
  const inspectTransaction = useCallback(
    async (txnId) => {
      if (!activeRunId || !txnId) return;
      try {
        const data = await fetchTransactionDetail(activeRunId, txnId);
        setSelectedTxnDetail(data);
      } catch (err) {
        setError(err.message);
      }
    },
    [activeRunId]
  );

  return {
    activeRunId,
    setActiveRunId,
    runs,
    setRuns,
    metrics,
    transactions,
    exceptions,
    selectedTxnDetail,
    setSelectedTxnDetail,
    inspectTransaction,
    refreshRuns,
    loading,
    error,
    setError,
  };
}
