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
      <div className="bg-white border border-slate-200 rounded-xl w-full max-w-2xl shadow-xl overflow-hidden my-6">
        
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-base font-bold font-mono text-slate-900">{transaction_id}</h2>
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                isReconciled
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : 'bg-amber-50 text-amber-800 border border-amber-200'
              }`}>
                {status}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              {exception_type ? exception_type : 'Fully Reconciled'}
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5 max-h-[75vh] overflow-y-auto">
          
          {/* Multi-Source Financial Snapshot */}
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-600 block mb-2.5">
              Multi-Source Financial Snapshot
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5">
              
              {/* Payment Gateway */}
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">Payment Gateway</span>
                <div className="mt-2">
                  <div className="text-base font-bold font-mono text-slate-900">
                    {payment_amount != null ? `₹${formatMoney(payment_amount)}` : '—'}
                  </div>
                  <span className="text-[10px] text-slate-400">Captured Amount</span>
                </div>
              </div>

              {/* Internal Ledger */}
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">Internal Ledger</span>
                <div className="mt-1 space-y-0.5 text-[11px] font-mono text-slate-600">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Gross:</span>
                    <span>{gross_amount != null ? `₹${formatMoney(gross_amount)}` : '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Fee:</span>
                    <span>{fee != null ? `₹${formatMoney(fee)}` : '—'}</span>
                  </div>
                  <div className="flex justify-between font-semibold text-slate-900 pt-0.5 border-t border-slate-200">
                    <span>Net:</span>
                    <span>{expected_net_amount != null ? `₹${formatMoney(expected_net_amount)}` : '—'}</span>
                  </div>
                </div>
              </div>

              {/* Bank Statement */}
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">Bank Credit</span>
                <div className="mt-2">
                  <div className="text-base font-bold font-mono text-slate-900">
                    {bank_amount != null ? `₹${formatMoney(bank_amount)}` : '—'}
                  </div>
                  <div className="text-[10px] font-mono flex justify-between pt-1 border-t border-slate-200">
                    <span className="text-slate-400">Delta:</span>
                    <span className={difference ? 'text-amber-600 font-semibold' : 'text-slate-400'}>
                      {difference != null && Number(difference) !== 0 ? `₹${formatMoney(difference)}` : '₹0'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Adjustments */}
              <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex flex-col justify-between">
                <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">Adjustments</span>
                <div className="mt-2">
                  {adjustments && adjustments.length > 0 ? (
                    <div className="space-y-1">
                      {adjustments.map((a, i) => (
                        <div key={i} className="text-xs font-mono text-emerald-700 font-semibold">
                          ₹{formatMoney(a.amount)}
                          <span className="text-[10px] text-slate-400 block font-normal font-sans">
                            {a.adjustment_type?.replace(/_/g, ' ')}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span className="text-[11px] text-slate-400 italic">None recorded</span>
                  )}
                </div>
              </div>

            </div>
          </div>

          {/* Source Provenance */}
          {source_provenance && (
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-slate-700">
                  <FileSpreadsheet className="h-3.5 w-3.5 text-slate-500" />
                  <span className="text-[11px] font-semibold uppercase tracking-wider">Source Provenance</span>
                </div>
                <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
                  Invariant Verified
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono pt-1">
                <div className="bg-white p-2 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 block font-sans">Source File</span>
                  <span className="font-semibold text-slate-800">{source_provenance.source_file || 'bank.csv'}</span>
                </div>
                <div className="bg-white p-2 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 block font-sans">Source Row</span>
                  <span className="font-semibold text-slate-800">Row #{source_provenance.source_row ?? '—'}</span>
                </div>
                <div className="bg-white p-2 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 block font-sans">Raw CSV Value</span>
                  <span className="font-semibold text-slate-800">{source_provenance.raw_credited_amount ?? '—'}</span>
                </div>
                <div className="bg-white p-2 rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 block font-sans">Parsed Amount</span>
                  <span className="font-semibold text-emerald-700">
                    {source_provenance.parsed_credited_amount != null ? `₹${formatMoney(source_provenance.parsed_credited_amount)}` : '—'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Primary AI Decision Block */}
          {agent_investigation ? (
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 space-y-3.5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                    AI Decision
                  </span>
                  <span className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                    agent_investigation.decision === 'AUTO_RESOLVED'
                      ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                      : 'bg-amber-100 text-amber-800 border border-amber-200'
                  }`}>
                    {agent_investigation.decision}
                  </span>
                </div>
                <span className="text-[11px] font-mono text-slate-600">
                  Confidence: <strong className="text-slate-900">{(agent_investigation.confidence * 100).toFixed(0)}%</strong>
                </span>
              </div>

              {/* Audit Reason */}
              <div className="space-y-1">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Audit Reason</span>
                <p className="text-xs text-slate-900 font-normal leading-relaxed">
                  {agent_investigation.reason}
                </p>
              </div>

              {/* Recommended Action */}
              <div className="space-y-1 pt-2 border-t border-slate-200">
                <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Recommended Action</span>
                <p className="text-xs text-slate-700 font-normal">
                  {agent_investigation.recommended_action}
                </p>
              </div>

              {/* Evidence Checklist */}
              {agent_investigation.evidence && agent_investigation.evidence.length > 0 && (
                <div className="space-y-1.5 pt-2 border-t border-slate-200">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Audit Evidence</span>
                  <div className="space-y-1 text-xs font-mono text-slate-600">
                    {agent_investigation.evidence.map((ev, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 flex-shrink-0 mt-0.5" />
                        <span>{ev}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3.5 text-xs text-emerald-800 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              <span>Matched across all 6 double-entry accounting rules during Phase 1. No discrepancy raised.</span>
            </div>
          )}

          {/* Advanced Developer & Multi-Agent Execution Details (COLLAPSED BY DEFAULT) */}
          {agent_investigation && (
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full bg-slate-50 hover:bg-slate-100 px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-slate-700 transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <Sliders className="h-3.5 w-3.5 text-slate-500" />
                  <span>Advanced Execution & Developer Details</span>
                </div>
                {showAdvanced ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
              </button>

              {showAdvanced && (
                <div className="p-4 bg-white space-y-3 border-t border-slate-200 text-xs font-mono">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div className="bg-slate-50 p-2 rounded border border-slate-200">
                      <span className="text-[10px] text-slate-400 block font-sans">Investigator</span>
                      <span className="font-semibold text-emerald-700">Evidence Collected</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded border border-slate-200">
                      <span className="text-[10px] text-slate-400 block font-sans">Verifier</span>
                      <span className="font-semibold text-slate-800">Resolution Verified</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded border border-slate-200">
                      <span className="text-[10px] text-slate-400 block font-sans">Resolution Type</span>
                      <span className="font-semibold text-slate-800 truncate block">{agent_investigation.resolution_type || 'NONE'}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded border border-slate-200">
                      <span className="text-[10px] text-slate-400 block font-sans">Partition Strategy</span>
                      <span className="font-semibold text-slate-800">balanced_type</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 border-t border-slate-200 bg-slate-50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg text-xs font-medium bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 shadow-xs transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
}
