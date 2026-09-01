/**
 * Centralized API client module for AI Finance Controller.
 * Provides typed/async fetch wrappers for backend REST endpoints.
 */

const BASE_URL = '';

async function handleResponse(res, errorMessage) {
  if (!res.ok) {
    let detail = '';
    try {
      const errJson = await res.json();
      detail = errJson.detail || errJson.message || '';
    } catch (_) {
      detail = await res.text().catch(() => '');
    }
    const msg = detail ? `${errorMessage}: ${detail}` : `${errorMessage} (Status ${res.status})`;
    throw new Error(msg);
  }
  return res.json();
}

export async function fetchRuns() {
  const res = await fetch(`${BASE_URL}/api/runs`);
  return handleResponse(res, 'Failed to fetch runs');
}

export async function fetchRunMetrics(runId) {
  if (!runId) return null;
  const res = await fetch(`${BASE_URL}/api/runs/${runId}/metrics`);
  return handleResponse(res, `Failed to fetch metrics for run ${runId}`);
}

export async function fetchRunTransactions(runId) {
  if (!runId) return [];
  const res = await fetch(`${BASE_URL}/api/runs/${runId}/transactions`);
  return handleResponse(res, `Failed to fetch transactions for run ${runId}`);
}

export async function fetchRunExceptions(runId) {
  if (!runId) return [];
  const res = await fetch(`${BASE_URL}/api/runs/${runId}/exceptions`);
  return handleResponse(res, `Failed to fetch exceptions for run ${runId}`);
}

export async function fetchTransactionDetail(runId, txnId) {
  if (!runId || !txnId) return null;
  const res = await fetch(`${BASE_URL}/api/runs/${runId}/transactions/${txnId}`);
  return handleResponse(res, `Failed to fetch detail for transaction ${txnId}`);
}

export async function startUploadReconciliation(formData) {
  const res = await fetch(`${BASE_URL}/api/runs/upload/start`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(res, 'Failed to start streaming reconciliation');
}

export async function uploadReconciliation(formData) {
  const res = await fetch(`${BASE_URL}/api/runs/upload`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(res, 'Failed to process uploaded dataset');
}

export async function validateDataset(formData) {
  const res = await fetch(`${BASE_URL}/api/runs/validate`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(res, 'Validation failed');
}

export async function fetchAuditLogs(runId) {
  if (!runId) return [];
  const res = await fetch(`${BASE_URL}/api/runs/${runId}/audit`);
  return handleResponse(res, `Failed to fetch audit logs for run ${runId}`);
}
