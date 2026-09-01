import React, { useState, useMemo } from 'react';
import { Search, Filter, ChevronRight, CheckCircle2, AlertTriangle, ArrowUpRight, Download, FileSpreadsheet, FileText, Printer } from 'lucide-react';

const formatMoney = (val) => {
  if (val === null || val === undefined || val === '') return '—';
  const num = Number(val);
  if (isNaN(num)) return String(val);
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: num % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  });
};

export default function ReconciliationTable({ transactions, exceptions, onSelectTransaction }) {
  const [activeTab, setActiveTab] = useState('ALL'); // ALL, RECONCILED, AUTO_RESOLVED, HUMAN_REVIEW
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');

  // Build unified items list
  const unifiedItems = useMemo(() => {
    if (!transactions) return [];

    const excMap = new Map();
    if (exceptions) {
      exceptions.forEach((e) => excMap.set(e.transaction_id, e));
    }

    return transactions.map((t) => {
      const exc = excMap.get(t.transaction_id);
      const isReconciled = t.status === 'RECONCILED';

      let decision = 'N/A';
      if (!isReconciled) {
        decision = exc?.decision || 'HUMAN_REVIEW';
      }

      const gtDecision = exc?.ground_truth_decision || exc?.expected_phase2_decision || t?.ground_truth_decision || t?.expected_phase2_decision;
      let matchStatus = null;
      if (gtDecision && decision !== 'N/A') {
        if (decision === 'NOT_EVALUATED') {
          matchStatus = 'NOT_EVALUATED';
        } else if (decision === gtDecision) {
          matchStatus = 'MATCH';
        } else {
          matchStatus = 'MISMATCH';
        }
      }

      return {
        transaction_id: t.transaction_id,
        status: t.status,
        exception_type: t.exception_type || 'None',
        decision: decision,
        ground_truth_decision: gtDecision,
        match_status: matchStatus,
        payment_amount: t.payment_amount ?? t.gross_amount ?? 0,
        bank_amount: t.bank_amount,
        difference: t.difference,
        confidence: exc?.confidence ?? (isReconciled ? 1.0 : 0.0),
        reason: exc?.reason || (isReconciled ? 'Reconciled successfully' : 'Pending review'),
        recommended_action: exc?.recommended_action || (isReconciled ? 'None' : ''),
        raw: t,
      };
    });
  }, [transactions, exceptions]);

  // Filtered dataset
  const filteredData = useMemo(() => {
    return unifiedItems.filter((item) => {
      // Tab filter
      if (activeTab === 'RECONCILED' && item.status !== 'RECONCILED') return false;
      if (activeTab === 'AUTO_RESOLVED' && item.decision !== 'AUTO_RESOLVED') return false;
      if (activeTab === 'HUMAN_REVIEW' && item.decision !== 'HUMAN_REVIEW') return false;

      // Category filter
      if (categoryFilter !== 'ALL' && item.exception_type !== categoryFilter) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          item.transaction_id.toLowerCase().includes(q) ||
          item.exception_type.toLowerCase().includes(q) ||
          item.reason.toLowerCase().includes(q) ||
          (item.recommended_action && item.recommended_action.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [unifiedItems, activeTab, categoryFilter, searchQuery]);

  // Exception categories for dropdown
  const categories = useMemo(() => {
    const set = new Set();
    unifiedItems.forEach((item) => {
      if (item.exception_type && item.exception_type !== 'None') {
        set.add(item.exception_type);
      }
    });
    return Array.from(set);
  }, [unifiedItems]);

  const tabs = [
    { key: 'ALL', label: 'All Transactions', count: unifiedItems.length },
    { key: 'RECONCILED', label: 'Reconciled', count: unifiedItems.filter((i) => i.status === 'RECONCILED').length },
    { key: 'AUTO_RESOLVED', label: 'Auto-Resolved', count: unifiedItems.filter((i) => i.decision === 'AUTO_RESOLVED').length },
    { key: 'HUMAN_REVIEW', label: 'Needs Attention', count: unifiedItems.filter((i) => i.decision === 'HUMAN_REVIEW').length },
  ];

  const handleDownloadCSV = () => {
    const dataToExport = filteredData.length > 0 ? filteredData : unifiedItems;
    if (dataToExport.length === 0) return;

    const headers = [
      'Transaction ID',
      'Status',
      'Exception Type',
      'Payment Amount (₹)',
      'Gross Amount (₹)',
      'Fee (₹)',
      'Expected Net (₹)',
      'Bank Amount (₹)',
      'Difference (₹)',
      'AI Decision',
      'Confidence (%)',
      'Audit Reason',
      'Recommended Action',
    ];

    const escapeCsv = (val) => {
      if (val === null || val === undefined) return '""';
      const str = String(val).replace(/"/g, '""');
      return `"${str}"`;
    };

    const rows = dataToExport.map((item) => {
      const raw = item.raw || {};
      return [
        escapeCsv(item.transaction_id),
        escapeCsv(item.status),
        escapeCsv(item.exception_type),
        escapeCsv(item.payment_amount ?? ''),
        escapeCsv(raw.gross_amount ?? ''),
        escapeCsv(raw.fee ?? ''),
        escapeCsv(raw.expected_net_amount ?? ''),
        escapeCsv(item.bank_amount ?? ''),
        escapeCsv(item.difference ?? 0),
        escapeCsv(item.decision),
        escapeCsv(item.confidence ? `${(item.confidence * 100).toFixed(0)}%` : ''),
        escapeCsv(item.reason),
        escapeCsv(item.recommended_action || ''),
      ].join(',');
    });

    const csvContent = [headers.join(','), ...rows].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `reconciliation_ledger_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleDownloadPDF = () => {
    const dataToExport = filteredData.length > 0 ? filteredData : unifiedItems;
    if (dataToExport.length === 0) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert('Please allow popups to generate and download the PDF report.');
      return;
    }

    const totalCount = dataToExport.length;
    const reconciledCount = dataToExport.filter((i) => i.status === 'RECONCILED').length;
    const autoResolvedCount = dataToExport.filter((i) => i.decision === 'AUTO_RESOLVED').length;
    const reviewCount = dataToExport.filter((i) => i.decision === 'HUMAN_REVIEW').length;

    const rowsHtml = dataToExport
      .map(
        (item, idx) => `
      <tr style="background-color: ${idx % 2 === 0 ? '#ffffff' : '#f8fafc'}; border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 8px 10px; font-family: monospace; font-weight: 600; font-size: 11px;">${item.transaction_id}</td>
        <td style="padding: 8px 10px; text-align: center;">
          <span style="display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; background: ${
            item.status === 'RECONCILED' ? '#ecfdf5; color: #065f46;' : '#fffbeb; color: #92400e;'
          }">${item.status}</span>
        </td>
        <td style="padding: 8px 10px; font-size: 11px; color: #475569;">${item.exception_type}</td>
        <td style="padding: 8px 10px; text-align: right; font-family: monospace; font-size: 11px;">₹${formatMoney(item.payment_amount)}</td>
        <td style="padding: 8px 10px; text-align: right; font-family: monospace; font-size: 11px;">₹${formatMoney(item.bank_amount)}</td>
        <td style="padding: 8px 10px; text-align: right; font-family: monospace; font-size: 11px; color: ${
          item.difference ? '#b45309; font-weight: 600;' : '#64748b;'
        }">₹${formatMoney(item.difference)}</td>
        <td style="padding: 8px 10px; text-align: center;">
          <span style="display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; ${
            item.decision === 'AUTO_RESOLVED'
              ? 'background: #ecfdf5; color: #065f46;'
              : item.decision === 'HUMAN_REVIEW'
              ? 'background: #fef2f2; color: #991b1b;'
              : 'color: #64748b;'
          }">${item.decision}</span>
        </td>
        <td style="padding: 8px 10px; font-size: 11px; color: #334155;">${item.reason || '—'}</td>
      </tr>`
      )
      .join('');

    const htmlContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Reconciliation Ledger - ${new Date().toLocaleDateString()}</title>
        <style>
          @page { size: landscape; margin: 12mm; }
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0f172a; margin: 0; padding: 16px; }
          .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 14px; }
          .title { font-size: 18px; font-weight: 700; margin: 0; color: #0f172a; }
          .subtitle { font-size: 11px; color: #64748b; margin-top: 3px; }
          .meta { text-align: right; font-size: 10px; color: #64748b; }
          .kpis { display: flex; gap: 10px; margin-bottom: 14px; }
          .kpi-card { flex: 1; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; }
          .kpi-label { font-size: 9px; text-transform: uppercase; color: #64748b; font-weight: 600; }
          .kpi-val { font-size: 15px; font-weight: 700; color: #0f172a; margin-top: 2px; }
          table { width: 100%; border-collapse: collapse; font-size: 11px; }
          th { background: #0f172a; color: #ffffff; text-align: left; padding: 8px 10px; font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
          th.right { text-align: right; }
          th.center { text-align: center; }
          .footer { margin-top: 16px; font-size: 10px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 8px; }
          @media print {
            body { padding: 0; }
            .no-print { display: none; }
          }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <h1 class="title">AI Finance Controller</h1>
            <p class="subtitle">Reconciliation Ledger & Financial Audit Report</p>
          </div>
          <div class="meta">
            <div><strong>Generated:</strong> ${new Date().toLocaleString()}</div>
            <div><strong>Records Included:</strong> ${totalCount}</div>
          </div>
        </div>

        <div class="kpis">
          <div class="kpi-card">
            <div class="kpi-label">Total Transactions</div>
            <div class="kpi-val">${totalCount}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Reconciled</div>
            <div class="kpi-val" style="color: #059669;">${reconciledCount}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">AI Auto-Resolved</div>
            <div class="kpi-val" style="color: #0284c7;">${autoResolvedCount}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Needs Attention</div>
            <div class="kpi-val" style="color: #d97706;">${reviewCount}</div>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th>Txn ID</th>
              <th class="center">Status</th>
              <th>Exception Category</th>
              <th class="right">Payment (₹)</th>
              <th class="right">Bank Credit (₹)</th>
              <th class="right">Difference (₹)</th>
              <th class="center">AI Decision</th>
              <th>Audit Reason</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>

        <div class="footer">
          Generated automatically by AI Finance Controller • Complete Multi-Source Audit Trail
        </div>

        <script>
          window.onload = function() {
            setTimeout(function() {
              window.print();
            }, 300);
          };
        </script>
      </body>
      </html>
    `;

    printWindow.document.open();
    printWindow.document.write(htmlContent);
    printWindow.document.close();
  };

  return (
    <div className="bg-background rounded-lg border border-border shadow-xs overflow-hidden">
      {/* Table Header & Controls */}
      <div className="p-6 border-b border-border space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-text">
              Reconciliation Ledger
            </h2>
            <p className="text-xs text-text-secondary mt-0.5">
              Multi-source record matching, discrepancy calculations, and agent investigation status
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
            {/* Search Input */}
            <div className="relative w-full sm:w-60">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-secondary/60" />
              <input
                type="text"
                placeholder="Search transactions..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-surface border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-text placeholder-text-secondary/60 outline-none focus:border-primary focus:bg-background transition-colors"
              />
            </div>

            {/* Export Actions */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleDownloadCSV}
                title="Download Reconciliation Ledger as CSV"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-surface hover:bg-surface-alt text-text border border-border transition-colors shadow-2xs cursor-pointer"
              >
                <FileSpreadsheet className="h-3.5 w-3.5 text-primary" />
                <span>CSV</span>
              </button>

              <button
                onClick={handleDownloadPDF}
                title="Download / Print Reconciliation Ledger as PDF"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-surface hover:bg-surface-alt text-text border border-border transition-colors shadow-2xs cursor-pointer"
              >
                <FileText className="h-3.5 w-3.5 text-accent-coral" />
                <span>PDF</span>
              </button>
            </div>
          </div>
        </div>

        {/* Filter Tabs & Category Selector */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
          {/* Tabs */}
          <div className="flex flex-wrap items-center gap-1 bg-surface-alt p-1 rounded-lg border border-border">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer ${
                  activeTab === tab.key
                    ? 'bg-background text-text shadow-xs font-semibold'
                    : 'text-text-secondary hover:text-text'
                }`}
              >
                {tab.label}
                <span className="ml-1.5 font-mono text-[10px] px-1.5 py-0.2 rounded bg-surface border border-border text-text-secondary">
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {/* Category Dropdown */}
          <div className="flex items-center gap-2 bg-surface border border-border px-3 py-1.5 rounded-lg text-xs">
            <Filter className="h-3 w-3 text-text-secondary/60" />
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="bg-transparent text-text font-medium outline-none cursor-pointer"
            >
              <option value="ALL" className="bg-background text-text">All Exception Types</option>
              {categories.map((cat) => (
                <option key={cat} value={cat} className="bg-background text-text">
                  {cat.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Table Data */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-border bg-surface text-text-secondary font-semibold text-[11px] uppercase tracking-wider">
              <th className="py-3 px-5">Transaction</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Exception</th>
              <th className="py-3 px-4 text-right">Payment</th>
              <th className="py-3 px-4 text-right">Bank</th>
              <th className="py-3 px-4 text-right">Difference</th>
              <th className="py-3 px-4 text-center">AI Decision</th>
              <th className="py-3 px-4 text-center">Ground Truth</th>
              <th className="py-3 px-4 text-center">Eval Match</th>
              <th className="py-3 px-4 text-center">Confidence</th>
              <th className="py-3 px-5 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-normal text-text-secondary">
            {filteredData.length === 0 ? (
              <tr>
                <td colSpan={11} className="py-10 text-center text-text-secondary/60 font-medium">
                  No matching transaction records found.
                </td>
              </tr>
            ) : (
              filteredData.map((item) => (
                <tr
                  key={item.transaction_id}
                  onClick={() => onSelectTransaction(item.transaction_id)}
                  className="hover:bg-surface cursor-pointer transition-colors group"
                >
                  {/* Transaction ID */}
                  <td className="py-3 px-5 font-mono font-semibold text-text group-hover:text-primary transition-colors">
                    {item.transaction_id}
                  </td>

                  {/* Status chip */}
                  <td className="py-3 px-4">
                    {item.status === 'RECONCILED' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono text-text bg-accent-green/10 border border-accent-green/30">
                        RECONCILED
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono text-text bg-accent-coral/10 border border-accent-coral/30">
                        EXCEPTION
                      </span>
                    )}
                  </td>

                  {/* Exception Category */}
                  <td className="py-3 px-4 font-mono text-[11px] text-text-secondary">
                    {item.exception_type !== 'None' ? item.exception_type : '—'}
                  </td>

                  {/* Payment Amount */}
                  <td className="py-3 px-4 text-right font-mono font-medium text-text">
                    {item.payment_amount != null ? `₹${formatMoney(item.payment_amount)}` : '—'}
                  </td>

                  {/* Bank Amount */}
                  <td className="py-3 px-4 text-right font-mono text-text-secondary">
                    {item.bank_amount != null ? `₹${formatMoney(item.bank_amount)}` : '—'}
                  </td>

                  {/* Difference */}
                  <td className="py-3 px-4 text-right font-mono">
                    {item.difference != null && Number(item.difference) !== 0 ? (
                      <span className="text-accent-coral font-medium">
                        ₹{formatMoney(item.difference)}
                      </span>
                    ) : (
                      <span className="text-text-secondary/60">₹0</span>
                    )}
                  </td>

                  {/* AI Decision */}
                  <td className="py-3 px-4 text-center">
                    {item.decision === 'AUTO_RESOLVED' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold text-text bg-accent-green/10 border border-accent-green/30">
                        AUTO-RESOLVED
                      </span>
                    )}
                    {item.decision === 'HUMAN_REVIEW' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold text-text bg-accent-coral/10 border border-accent-coral/30">
                        HUMAN REVIEW
                      </span>
                    )}
                    {item.decision === 'NOT_EVALUATED' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold text-text bg-surface-alt border border-border">
                        NOT EVALUATED
                      </span>
                    )}
                    {item.decision === 'N/A' && (
                      <span className="text-text-secondary/60 text-[11px] font-mono">—</span>
                    )}
                  </td>

                  {/* Ground Truth */}
                  <td className="py-3 px-4 text-center font-mono text-[11px]">
                    {item.ground_truth_decision ? (
                      <span className="text-text font-medium">{item.ground_truth_decision}</span>
                    ) : (
                      <span className="text-text-secondary/60">—</span>
                    )}
                  </td>

                  {/* Ground Truth Evaluation Match */}
                  <td className="py-3 px-4 text-center font-mono text-[10px]">
                    {item.match_status === 'MATCH' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-semibold text-text bg-accent-green/10 border border-accent-green/30">
                        ✓ MATCH
                      </span>
                    )}
                    {item.match_status === 'MISMATCH' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-semibold text-rose-800 bg-rose-100 border border-rose-200">
                        ✗ MISMATCH
                      </span>
                    )}
                    {item.match_status === 'NOT_EVALUATED' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-semibold text-text bg-accent-coral/10 border border-accent-coral/30">
                        ! UNTESTED
                      </span>
                    )}
                    {!item.match_status && <span className="text-text-secondary/60">—</span>}
                  </td>

                  {/* Confidence */}
                  <td className="py-3 px-4 text-center font-mono text-[11px]">
                    {item.decision !== 'N/A' ? (
                      <span className="text-text font-medium">
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    ) : (
                      <span className="text-text-secondary/60">—</span>
                    )}
                  </td>

                  {/* Action */}
                  <td className="py-3 px-5 text-right text-text-secondary/60 group-hover:text-primary transition-colors">
                    <ChevronRight className="h-4 w-4 ml-auto" />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Table Footer */}
      <div className="p-4 border-t border-border bg-surface text-xs text-text-secondary flex flex-col sm:flex-row justify-between items-center gap-2">
        <span>Showing {filteredData.length} of {unifiedItems.length} transactions</span>
        <span className="text-[11px] font-mono text-text-secondary">Click any row to inspect multi-source evidence</span>
      </div>
    </div>
  );
}
