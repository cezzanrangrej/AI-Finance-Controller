import React from 'react';
import { Play, RefreshCw, PanelLeft, PanelLeftClose, CheckCircle2, Loader2, AlertCircle, Database } from 'lucide-react';

export default function Header({
  onRunReconciliation,
  workflowState,
  datasetSource,
  isSidebarOpen,
  onToggleSidebar,
}) {
  const isRunning = workflowState === 'RUNNING_PHASE_1' || workflowState === 'RUNNING_AI' || workflowState === 'VALIDATING';

  const getStatusBadge = () => {
    switch (workflowState) {
      case 'RUNNING_PHASE_1':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-amber-50 text-amber-800 border border-amber-200">
            <Loader2 className="h-3 w-3 animate-spin text-amber-600" />
            Phase 1 Processing
          </span>
        );
      case 'RUNNING_AI':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
            <Loader2 className="h-3 w-3 animate-spin text-emerald-600" />
            AI Investigating
          </span>
        );
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="h-3 w-3 text-emerald-600" />
            Reconciliation Complete
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-rose-50 text-rose-800 border border-rose-200">
            <AlertCircle className="h-3 w-3 text-rose-600" />
            Reconciliation Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Ready for Reconciliation
          </span>
        );
    }
  };

  return (
    <header className="h-16 border-b border-slate-200 bg-white sticky top-0 z-30 px-4 sm:px-6 flex items-center justify-between">
      {/* Left: Sidebar Toggle & Page context */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          title={isSidebarOpen ? 'Close Sidebar' : 'Open Sidebar'}
          className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
        >
          {isSidebarOpen ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeft className="h-5 w-5" />}
        </button>

        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-sm font-bold tracking-tight text-slate-900 uppercase">
              AI Finance Controller
            </h1>
            
            {/* Status Badge */}
            <div className="hidden sm:block">
              {getStatusBadge()}
            </div>

            {/* Dataset Badge */}
            <div className="hidden md:flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-slate-600 bg-slate-50 border border-slate-200">
              <Database className="h-3 w-3 text-slate-400" />
              <span>{datasetSource || 'Standard Dataset'}</span>
            </div>
          </div>
          <p className="text-[11px] text-slate-500 font-normal hidden sm:block">
            Autonomous multi-source financial reconciliation & exception investigation
          </p>
        </div>
      </div>

      {/* Right: Single Primary Action */}
      <div className="flex items-center gap-3">
        <button
          onClick={onRunReconciliation}
          disabled={isRunning}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all shadow-xs cursor-pointer ${
            isRunning
              ? 'bg-slate-100 text-slate-400 cursor-not-allowed border border-slate-200'
              : 'bg-emerald-600 hover:bg-emerald-700 text-white active:translate-y-px'
          }`}
        >
          {isRunning ? (
            <>
              <RefreshCw className="h-3.5 w-3.5 animate-spin text-white" />
              <span>Running...</span>
            </>
          ) : (
            <>
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>Run Reconciliation</span>
            </>
          )}
        </button>
      </div>
    </header>
  );
}
