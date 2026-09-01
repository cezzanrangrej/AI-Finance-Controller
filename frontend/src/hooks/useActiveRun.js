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
      } else if (data.length > 0) {
        setActiveRunId((prev) => (prev && data.some((r) => r.run_id === prev) ? prev : data[0].run_id));
      } else {
        setActiveRunId(null);
        setMetrics(null);
        setTransactions([]);
        setExceptions([]);
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
