import React, { useState } from 'react';
import { X, CheckCircle2, AlertTriangle, ShieldCheck, ArrowRight, FileSpreadsheet, ChevronDown, ChevronUp, Cpu, Sliders } from 'lucide-react';

const formatMoney = (val) => {
  if (val === null || val === undefined || val === '') return '—';
  const num = Number(val);
  if (isNaN(num)) return String(val);
  return num.toLocaleString('en-IN', {
    minimumFractionDigits: num % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  });
};

export default function ExceptionDetailModal({ detail, onClose }) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  if (!detail) return null;

  const {
    transaction_id,
    status,
    exception_type,
    payment_amount,
    gross_amount,
    fee,
    expected_net_amount,
    bank_amount,
    difference,
    adjustments,
    agent_investigation,
    source_provenance,
  } = detail;

  const isReconciled = status === 'RECONCILED';

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-background border border-border rounded-xl w-full max-w-2xl shadow-xl overflow-hidden my-6">
        
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-surface">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-base font-bold font-mono text-text">{transaction_id}</h2>
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${
                isReconciled
                  ? 'bg-accent-green/10 text-text border-accent-green/30'
                  : 'bg-accent-coral/10 text-text border-accent-coral/30'
              }`}>
                {status}
              </span>
            </div>
            <p className="text-xs text-text-secondary mt-0.5 font-mono">
              {exception_type ? exception_type : 'Fully Reconciled'}
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-text-secondary/60 hover:text-text hover:bg-surface-alt transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5 max-h-[75vh] overflow-y-auto">
          
          {/* Multi-Source Financial Snapshot */}
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary block mb-2.5">
              Multi-Source Financial Snapshot
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5">
              
              {/* Payment Gateway */}
              <div className="bg-surface border border-border p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-text-secondary/60 uppercase tracking-wider">Payment Gateway</span>
                <div className="mt-2">
                  <div className="text-base font-bold font-mono text-text">
                    {payment_amount != null ? `₹${formatMoney(payment_amount)}` : '—'}
                  </div>
                  <span className="text-[10px] text-text-secondary/60">Captured Amount</span>
                </div>
              </div>

              {/* Internal Ledger */}
              <div className="bg-surface border border-border p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-text-secondary/60 uppercase tracking-wider">Internal Ledger</span>
                <div className="mt-1 space-y-0.5 text-[11px] font-mono text-text-secondary">
                  <div className="flex justify-between">
                    <span className="text-text-secondary/60">Gross:</span>
                    <span>{gross_amount != null ? `₹${formatMoney(gross_amount)}` : '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary/60">Fee:</span>
                    <span>{fee != null ? `₹${formatMoney(fee)}` : '—'}</span>
                  </div>
                  <div className="flex justify-between font-semibold text-text pt-0.5 border-t border-border">
                    <span>Net:</span>
                    <span>{expected_net_amount != null ? `₹${formatMoney(expected_net_amount)}` : '—'}</span>
                  </div>
                </div>
              </div>

              {/* Bank Statement */}
              <div className="bg-surface border border-border p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-text-secondary/60 uppercase tracking-wider">Bank Credit</span>
                <div className="mt-2">
                  <div className="text-base font-bold font-mono text-text">
                    {bank_amount != null ? `₹${formatMoney(bank_amount)}` : '—'}
                  </div>
                  <div className="text-[10px] font-mono flex justify-between pt-1 border-t border-border">
                    <span className="text-text-secondary/60">Delta:</span>
                    <span className={difference ? 'text-accent-coral font-semibold' : 'text-text-secondary/60'}>
                      {difference != null && Number(difference) !== 0 ? `₹${formatMoney(difference)}` : '₹0'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Adjustments */}
              <div className="bg-surface border border-border p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-text-secondary/60 uppercase tracking-wider">Adjustments</span>
                <div className="mt-2">
                  {adjustments && adjustments.length > 0 ? (
                    <div className="space-y-1">
                      {adjustments.map((a, i) => (
                        <div key={i} className="text-xs font-mono text-primary font-semibold">
                          ₹{formatMoney(a.amount)}
                          <span className="text-[10px] text-text-secondary/60 block font-normal font-sans">
                            {a.adjustment_type?.replace(/_/g, ' ')}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span className="text-[11px] text-text-secondary/60 italic">None recorded</span>
                  )}
                </div>
              </div>

            </div>
          </div>

          {/* Source Provenance */}
          {source_provenance && (
            <div className="bg-surface border border-border rounded-lg p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-text">
                  <FileSpreadsheet className="h-3.5 w-3.5 text-text-secondary" />
                  <span className="text-[11px] font-semibold uppercase tracking-wider">Source Provenance</span>
                </div>
                <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-accent-green/10 text-text border border-accent-green/30">
                  Invariant Verified
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono pt-1">
                <div className="bg-background p-2 rounded border border-border">
                  <span className="text-[10px] text-text-secondary/60 block font-sans">Source File</span>
                  <span className="font-semibold text-text">{source_provenance.source_file || 'bank.csv'}</span>
                </div>
                <div className="bg-background p-2 rounded border border-border">
                  <span className="text-[10px] text-text-secondary/60 block font-sans">Source Row</span>
                  <span className="font-semibold text-text">Row #{source_provenance.source_row ?? '—'}</span>
                </div>
                <div className="bg-background p-2 rounded border border-border">
                  <span className="text-[10px] text-text-secondary/60 block font-sans">Raw CSV Value</span>
                  <span className="font-semibold text-text">{source_provenance.raw_credited_amount ?? '—'}</span>
                </div>
                <div className="bg-background p-2 rounded border border-border">
                  <span className="text-[10px] text-text-secondary/60 block font-sans">Parsed Amount</span>
                  <span className="font-semibold text-primary">
                    {source_provenance.parsed_credited_amount != null ? `₹${formatMoney(source_provenance.parsed_credited_amount)}` : '—'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Primary AI Decision Block */}
          {agent_investigation ? (
            <div className="bg-surface border border-border rounded-lg p-4 space-y-3.5">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                    AI Decision
                  </span>
                  <span className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-bold border ${
                    agent_investigation.decision === 'AUTO_RESOLVED'
                      ? 'bg-accent-green/10 text-text border-accent-green/30'
                      : 'bg-accent-coral/10 text-text border-accent-coral/30'
                  }`}>
                    {agent_investigation.decision}
                  </span>
                </div>
                <span className="text-[11px] font-mono text-text-secondary">
                  Confidence: <strong className="text-text">{(agent_investigation.confidence * 100).toFixed(0)}%</strong>
                </span>
              </div>

              {/* Audit Reason */}
              <div className="space-y-1">
                <span className="text-[10px] font-semibold text-text-secondary/60 uppercase tracking-wider">Audit Reason</span>
                <p className="text-xs text-text font-normal leading-relaxed">
                  {agent_investigation.reason}
                </p>
              </div>

              {/* Recommended Action */}
              <div className="space-y-1 pt-2 border-t border-border">
                <span className="text-[10px] font-semibold text-text-secondary/60 uppercase tracking-wider">Recommended Action</span>
                <p className="text-xs text-text-secondary font-normal">
                  {agent_investigation.recommended_action}
                </p>
              </div>

              {/* Evidence Checklist */}
              {agent_investigation.evidence && agent_investigation.evidence.length > 0 && (
                <div className="space-y-1.5 pt-2 border-t border-border">
                  <span className="text-[10px] font-semibold text-text-secondary/60 uppercase tracking-wider">Audit Evidence</span>
                  <div className="space-y-1 text-xs font-mono text-text-secondary">
                    {agent_investigation.evidence.map((ev, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <CheckCircle2 className="h-3.5 w-3.5 text-text flex-shrink-0 mt-0.5" />
                        <span>{ev}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-accent-green/10 border border-accent-green/30 rounded-lg p-3.5 text-xs text-text flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-text" />
              <span>Matched across all 6 double-entry accounting rules during Phase 1. No discrepancy raised.</span>
            </div>
          )}

          {/* Advanced Developer & Multi-Agent Execution Details (COLLAPSED BY DEFAULT) */}
          {agent_investigation && (
            <div className="border border-border rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full bg-surface hover:bg-surface-alt px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-text transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <Sliders className="h-3.5 w-3.5 text-accent-purple" />
                  <span>Advanced Execution & Developer Details</span>
                </div>
                {showAdvanced ? <ChevronUp className="h-4 w-4 text-text-secondary/60" /> : <ChevronDown className="h-4 w-4 text-text-secondary/60" />}
              </button>

              {showAdvanced && (
                <div className="p-4 bg-background space-y-3 border-t border-border text-xs font-mono">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div className="bg-surface p-2 rounded border border-border">
                      <span className="text-[10px] text-text-secondary/60 block font-sans">Architecture</span>
                      <span className="font-semibold text-accent-purple">Multi-Agent Batch</span>
                    </div>
                    <div className="bg-surface p-2 rounded border border-border">
                      <span className="text-[10px] text-text-secondary/60 block font-sans">Resolution Type</span>
                      <span className="font-semibold text-text truncate block">{agent_investigation.resolution_type || 'NONE'}</span>
                    </div>
                    <div className="bg-surface p-2 rounded border border-border">
                      <span className="text-[10px] text-text-secondary/60 block font-sans">Evidence Scope</span>
                      <span className="font-semibold text-text">4-Source Prefetch</span>
                    </div>
                    <div className="bg-surface p-2 rounded border border-border">
                      <span className="text-[10px] text-text-secondary/60 block font-sans">Partitioning</span>
                      <span className="font-semibold text-text">Balanced Type</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 border-t border-border bg-surface flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg text-xs font-medium bg-background hover:bg-surface-alt text-text border border-border shadow-xs transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
}
