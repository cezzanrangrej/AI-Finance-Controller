import React, { useState, useRef, useEffect } from 'react';
import { Play, RefreshCw, PanelLeft, PanelLeftClose, CheckCircle2, Loader2, AlertCircle, Database, Download, FileText, FileCode, ChevronDown } from 'lucide-react';

export default function Header({
  activeRunId,
  onRunReconciliation,
  workflowState,
  progressState,
  datasetSource,
  isSidebarOpen,
  onToggleSidebar,
}) {
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const menuRef = useRef(null);
  const isRunning =
    workflowState === 'RUNNING_PHASE_1' ||
    workflowState === 'RUNNING_AI' ||
    workflowState === 'VALIDATING' ||
    workflowState === 'UPLOADING' ||
    progressState?.stage === 'UPLOADING' ||
    progressState?.stage === 'PHASE_1' ||
    progressState?.stage === 'PHASE_2';

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowDownloadMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getStatusBadge = () => {
    if (progressState?.stage === 'UPLOADING') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-primary/10 text-text border border-primary/30">
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
          Uploading & Parsing CSVs...
        </span>
      );
    }
    if (progressState?.stage === 'PHASE_1' || workflowState === 'RUNNING_PHASE_1') {
      const p1 = progressState?.phase1;
      const label = p1
        ? `Phase 1: ${p1.reconciled}/${p1.total} reconciled, ${p1.exceptions} flagged`
        : progressState?.totalRecords
        ? `Phase 1: Processing ${progressState.totalRecords} records`
        : 'Phase 1 Processing...';
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-accent-coral/10 text-text border border-accent-coral/30">
          <Loader2 className="h-3 w-3 animate-spin text-accent-coral" />
          {label}
        </span>
      );
    }
    if (progressState?.stage === 'PHASE_2' || workflowState === 'RUNNING_AI') {
      const p2 = progressState?.phase2;
      const label =
        p2 && p2.batchesTotal > 0
          ? `Phase 2: batch ${p2.batchesDone}/${p2.batchesTotal} — ${p2.resolved} resolved, ${p2.humanReview} escalated`
          : 'Phase 2: AI Multi-Agent Investigating...';
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-accent-purple/10 text-text border border-accent-purple/30">
          <Loader2 className="h-3 w-3 animate-spin text-accent-purple" />
          {label}
        </span>
      );
    }
    if (progressState?.stage === 'COMPLETED' || workflowState === 'COMPLETED') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-accent-green/10 text-text border border-accent-green/30">
          <CheckCircle2 className="h-3 w-3 text-text" />
          Reconciliation Complete
        </span>
      );
    }
    if (progressState?.stage === 'FAILED' || workflowState === 'FAILED') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-rose-50 text-rose-800 border border-rose-200">
          <AlertCircle className="h-3 w-3 text-rose-600" />
          Reconciliation Failed
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-surface-alt text-text-secondary border border-border">
        <span className="h-1.5 w-1.5 rounded-full bg-primary" />
        Ready for Reconciliation
      </span>
    );
  };

  return (
    <header className="h-16 border-b border-border bg-background sticky top-0 z-30 px-4 sm:px-6 flex items-center justify-between">
      {/* Left: Sidebar Toggle & Page context */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          title={isSidebarOpen ? 'Close Sidebar' : 'Open Sidebar'}
          className="p-1.5 rounded-lg border border-border text-text-secondary hover:bg-surface transition-colors cursor-pointer"
        >
          {isSidebarOpen ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeft className="h-5 w-5" />}
        </button>

        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-sm font-bold tracking-tight text-text uppercase">
              AI Finance Controller
            </h1>
            
            {/* Status Badge */}
            <div className="hidden sm:block">
              {getStatusBadge()}
            </div>

            {/* Dataset Badge */}
            <div className="hidden md:flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-text-secondary bg-surface border border-border">
              <Database className="h-3 w-3 text-text-secondary/60" />
              <span>{datasetSource || 'No dataset loaded'}</span>
            </div>
          </div>
          <p className="text-[11px] text-text-secondary font-normal hidden sm:block">
            Autonomous multi-source financial reconciliation & exception investigation
          </p>
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-3">
        {activeRunId && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setShowDownloadMenu(!showDownloadMenu)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold tracking-wide bg-background border border-border hover:bg-surface text-text shadow-xs transition-colors cursor-pointer"
              title="Download Reconciliation Report"
            >
              <Download className="h-3.5 w-3.5 text-text-secondary" />
              <span>Download Report</span>
              <ChevronDown className="h-3 w-3 text-text-secondary/60" />
            </button>

            {showDownloadMenu && (
              <div className="absolute right-0 mt-1.5 w-56 bg-background rounded-lg shadow-lg border border-border py-1 z-50 animate-in fade-in-50 duration-100">
                <div className="px-3 py-1.5 border-b border-border text-[10px] uppercase font-semibold text-text-secondary/60">
                  Export Options
                </div>
                <a
                  href={`/api/runs/${activeRunId}/report?format=markdown&download=true`}
                  download={`reconciliation_report_${activeRunId}.md`}
                  onClick={() => setShowDownloadMenu(false)}
                  className="flex items-center gap-2.5 px-3 py-2 text-xs text-text hover:bg-surface hover:text-primary transition-colors"
                >
                  <FileText className="h-4 w-4 text-primary" />
                  <div>
                    <span className="font-medium block">Executive Report (.md)</span>
                    <span className="text-[10px] text-text-secondary/60 block font-normal">Formatted Markdown audit summary</span>
                  </div>
                </a>
                <a
                  href={`/api/runs/${activeRunId}/report?format=json&download=true`}
                  download={`reconciliation_report_${activeRunId}.json`}
                  onClick={() => setShowDownloadMenu(false)}
                  className="flex items-center gap-2.5 px-3 py-2 text-xs text-text hover:bg-surface hover:text-primary transition-colors"
                >
                  <FileCode className="h-4 w-4 text-accent-purple" />
                  <div>
                    <span className="font-medium block">Structured Data (.json)</span>
                    <span className="text-[10px] text-text-secondary/60 block font-normal">Complete JSON metrics and traces</span>
                  </div>
                </a>
              </div>
            )}
          </div>
        )}

        <button
          onClick={onRunReconciliation}
          disabled={isRunning}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all shadow-xs cursor-pointer ${
            isRunning
              ? 'bg-surface-alt text-text-secondary/60 cursor-not-allowed border border-border'
              : 'bg-primary hover:bg-primary-light text-white active:translate-y-px'
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
