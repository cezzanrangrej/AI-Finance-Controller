import React from 'react';
import { X, CheckCircle2, Bot, ShieldAlert, FileText, Activity, AlertCircle } from 'lucide-react';

export default function ExceptionDetailModal({ detail, onClose }) {
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
  } = detail;

  const isReconciled = status === 'RECONCILED';

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-3xl shadow-2xl overflow-hidden my-8 animate-in fade-in zoom-in duration-200">
        
        {/* Modal Header */}
        <div className="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-950/40">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <FileText className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold font-mono text-white">{transaction_id}</h2>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                  isReconciled
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                }`}>
                  {status}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-mono">
                {exception_type ? exception_type : 'Fully Reconciled'}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body Content */}
        <div className="p-6 space-y-6 max-h-[80vh] overflow-y-auto">
          
          {/* 4-Source Financial Comparison Grid */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
              Multi-Source Financial Snapshot (Payments, Ledger, Bank, Adjustments)
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {/* Payment Card */}
              <div className="bg-slate-950 border border-slate-800 p-3.5 rounded-2xl space-y-1.5">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">1. Payment Gateway</span>
                <div className="text-lg font-extrabold font-mono text-white">
                  {payment_amount != null ? `₹${payment_amount.toLocaleString()}` : 'N/A'}
                </div>
                <p className="text-[10px] text-slate-500">Captured Amount</p>
              </div>

              {/* Ledger Card */}
              <div className="bg-slate-950 border border-slate-800 p-3.5 rounded-2xl space-y-1">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">2. Internal Ledger</span>
                <div className="text-[11px] space-y-0.5 font-mono text-slate-300">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Gross:</span>
                    <span>{gross_amount != null ? `₹${gross_amount.toLocaleString()}` : 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Fee:</span>
                    <span>{fee != null ? `₹${fee.toLocaleString()}` : 'N/A'}</span>
                  </div>
                  <div className="flex justify-between font-bold text-indigo-400 pt-0.5 border-t border-slate-800">
                    <span>Net:</span>
                    <span>{expected_net_amount != null ? `₹${expected_net_amount.toLocaleString()}` : 'N/A'}</span>
                  </div>
                </div>
              </div>

              {/* Bank Card */}
              <div className="bg-slate-950 border border-slate-800 p-3.5 rounded-2xl space-y-1.5">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">3. Bank Statement</span>
                <div className="text-lg font-extrabold font-mono text-white">
                  {bank_amount != null ? `₹${bank_amount.toLocaleString()}` : 'N/A'}
                </div>
                <div className="text-[10px] font-mono flex justify-between pt-0.5 border-t border-slate-800">
                  <span className="text-slate-500">Diff:</span>
                  <span className={difference ? 'text-amber-400 font-bold' : 'text-slate-400'}>
                    {difference != null ? `₹${difference.toLocaleString()}` : '₹0'}
                  </span>
                </div>
              </div>

              {/* Adjustments Card */}
              <div className="bg-slate-950 border border-slate-800 p-3.5 rounded-2xl space-y-1.5">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">4. Adjustments</span>
                {adjustments && adjustments.length > 0 ? (
                  <div className="space-y-1">
                    {adjustments.map((a, i) => (
                      <div key={i} className="text-[11px] font-mono text-emerald-400 font-bold">
                        ₹{a.amount?.toLocaleString()} ({a.adjustment_type?.replace(/_/g, ' ')})
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-[11px] text-slate-500 font-mono italic">
                    No adjustments found
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* AI Decision Block */}
          {agent_investigation ? (
            <div className={`p-5 rounded-2xl border ${
              agent_investigation.decision === 'AUTO_RESOLVED'
                ? 'bg-indigo-950/20 border-indigo-500/30'
                : 'bg-amber-950/20 border-amber-500/30'
            } space-y-4`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {agent_investigation.decision === 'AUTO_RESOLVED' ? (
                    <>
                      <Bot className="h-5 w-5 text-indigo-400" />
                      <span className="text-sm font-bold text-indigo-200">AI DECISION: AUTO RESOLVED</span>
                    </>
                  ) : (
                    <>
                      <ShieldAlert className="h-5 w-5 text-amber-400" />
                      <span className="text-sm font-bold text-amber-200">AI DECISION: NEEDS HUMAN REVIEW</span>
                    </>
                  )}
                </div>
                <div className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-950/80 border border-slate-800 text-slate-200">
                  Confidence: {(agent_investigation.confidence * 100).toFixed(0)}%
                </div>
              </div>

              {/* Reasoning */}
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Reason</span>
                <p className="text-xs text-slate-200 leading-relaxed font-medium">
                  {agent_investigation.reason}
                </p>
              </div>

              {/* Recommended Action */}
              <div className="space-y-1 pt-2 border-t border-slate-800/60">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Recommended Action</span>
                <p className="text-xs text-indigo-300 font-medium">
                  {agent_investigation.recommended_action}
                </p>
              </div>

              {/* Evidence Checklist */}
              {agent_investigation.evidence && agent_investigation.evidence.length > 0 && (
                <div className="pt-2 border-t border-slate-800/60 space-y-2">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Audit Evidence Checklist</span>
                  <div className="space-y-1.5 text-xs font-mono text-slate-300">
                    {agent_investigation.evidence.map((ev, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                        <span>{ev}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-4 rounded-2xl bg-emerald-950/20 border border-emerald-500/30 text-xs text-emerald-300 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span>Transaction matched perfectly across all sources during Phase 1. No exception raised.</span>
            </div>
          )}

          {/* Audit Timeline */}
          <div className="space-y-3 pt-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Activity className="h-4 w-4 text-indigo-400" /> Audit Timeline
            </h3>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex items-center gap-3 bg-slate-950/80 p-2.5 rounded-xl border border-slate-800">
                <span className="h-2 w-2 rounded-full bg-slate-500" />
                <span className="text-slate-400">1. INGESTION</span>
                <span className="text-slate-300 ml-auto">Data loaded across payments, ledger, bank, & adjustments</span>
              </div>
              <div className="flex items-center gap-3 bg-slate-950/80 p-2.5 rounded-xl border border-slate-800">
                <span className={`h-2 w-2 rounded-full ${isReconciled ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                <span className="text-slate-400">2. PHASE 1 ENGINE</span>
                <span className="text-slate-300 ml-auto">
                  {isReconciled ? 'Reconciled successfully' : `Flagged: ${exception_type}`}
                </span>
              </div>
              {agent_investigation && (
                <div className="flex items-center gap-3 bg-slate-950/80 p-2.5 rounded-xl border border-slate-800">
                  <span className={`h-2 w-2 rounded-full ${agent_investigation.decision === 'AUTO_RESOLVED' ? 'bg-indigo-400' : 'bg-amber-400'}`} />
                  <span className="text-slate-400">3. PHASE 2 AI AGENT</span>
                  <span className="text-slate-300 ml-auto">
                    Investigated → {agent_investigation.decision}
                  </span>
                </div>
              )}
            </div>
          </div>

        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/60 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-white transition-colors"
          >
            Close Detail View
          </button>
        </div>

      </div>
    </div>
  );
}
