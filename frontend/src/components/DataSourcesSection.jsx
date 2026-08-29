import React, { useState, useRef } from 'react';
import {
  Upload,
  FileCheck,
  AlertCircle,
  CheckCircle2,
  Database,
  Play,
  Info,
  ShieldCheck
} from 'lucide-react';

export default function DataSourcesSection({
  files,
  setFiles,
  onRunReconciliation,
  workflowState,
}) {
  const [validationStatus, setValidationStatus] = useState(null);
  const [validating, setValidating] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  const paymentsInputRef = useRef(null);
  const ledgerInputRef = useRef(null);
  const bankInputRef = useRef(null);
  const adjustmentsInputRef = useRef(null);

  const isRunning = workflowState === 'RUNNING_PHASE_1' || workflowState === 'RUNNING_AI' || workflowState === 'VALIDATING';

  const handleFileChange = (sourceKey, e) => {
    const file = e.target.files?.[0] || null;
    setFiles((prev) => ({ ...prev, [sourceKey]: file }));
    setValidationStatus(null);
    setUploadError(null);
  };

  const handleDrop = (sourceKey, e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0] || null;
    if (file) {
      setFiles((prev) => ({ ...prev, [sourceKey]: file }));
      setValidationStatus(null);
      setUploadError(null);
    }
  };

  const handleValidate = async () => {
    if (!files.payments || !files.ledger || !files.bank) {
      setUploadError('Please upload Payments, Ledger, and Bank CSV files to validate.');
      return;
    }

    try {
      setValidating(true);
      setUploadError(null);

      const formData = new FormData();
      if (files.payments) formData.append('payments', files.payments);
      if (files.ledger) formData.append('ledger', files.ledger);
      if (files.bank) formData.append('bank', files.bank);
      if (files.adjustments) formData.append('adjustments', files.adjustments);

      const res = await fetch('/api/runs/validate', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setValidationStatus(data);
      } else {
        const err = await res.json();
        setUploadError(err.detail || 'Validation failed');
      }
    } catch (err) {
      setUploadError('Network error validating dataset.');
    } finally {
      setValidating(false);
    }
  };

  const allRequiredPresent = Boolean(files.payments && files.ledger && files.bank);

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-xs space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Financial Data Sources</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Upload your payment gateway export, ERP general ledger, and bank settlement statements.
          </p>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-50 border border-slate-200 text-xs font-mono text-slate-600 self-start sm:self-auto">
          <Database className="h-3.5 w-3.5 text-slate-400" />
          <span>4-Source Double-Entry Verification</span>
        </div>
      </div>

      {/* Validation Error Banner */}
      {uploadError && (
        <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs font-medium flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-rose-600 flex-shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}

      {/* 4 Upload Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Payments Card */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => handleDrop('payments', e)}
          className={`border-2 border-dashed rounded-lg p-4 flex flex-col justify-between transition-colors bg-slate-50/50 ${
            files.payments ? 'border-emerald-400 bg-emerald-50/20' : 'border-slate-300 hover:border-slate-400'
          }`}
        >
          <div>
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="font-semibold text-slate-900">1. PAYMENTS</span>
              <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                Required
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mb-3">
              Gateway transactions (`transaction_id`, `amount`)
            </p>
          </div>

          <div>
            <input
              type="file"
              accept=".csv,text/csv"
              ref={paymentsInputRef}
              onChange={(e) => handleFileChange('payments', e)}
              className="hidden"
            />

            {files.payments ? (
              <div className="bg-white border border-emerald-200 p-2.5 rounded-md text-xs space-y-1">
                <div className="flex items-center gap-1.5 text-emerald-700 font-medium truncate">
                  <FileCheck className="h-4 w-4 flex-shrink-0 text-emerald-600" />
                  <span className="truncate">{files.payments.name}</span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-500">
                  <span>{(files.payments.size / 1024).toFixed(1)} KB</span>
                  <button
                    type="button"
                    onClick={() => paymentsInputRef.current?.click()}
                    className="text-emerald-600 hover:underline font-medium cursor-pointer"
                  >
                    Replace
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => paymentsInputRef.current?.click()}
                className="w-full py-2.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-md text-xs font-medium text-slate-700 shadow-xs transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <Upload className="h-3.5 w-3.5 text-slate-400" />
                <span>payments.csv</span>
              </button>
            )}
          </div>
        </div>

        {/* Ledger Card */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => handleDrop('ledger', e)}
          className={`border-2 border-dashed rounded-lg p-4 flex flex-col justify-between transition-colors bg-slate-50/50 ${
            files.ledger ? 'border-emerald-400 bg-emerald-50/20' : 'border-slate-300 hover:border-slate-400'
          }`}
        >
          <div>
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="font-semibold text-slate-900">2. LEDGER</span>
              <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                Required
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mb-3">
              ERP records (`transaction_id`, `gross_amount`, `fee`)
            </p>
          </div>

          <div>
            <input
              type="file"
              accept=".csv,text/csv"
              ref={ledgerInputRef}
              onChange={(e) => handleFileChange('ledger', e)}
              className="hidden"
            />

            {files.ledger ? (
              <div className="bg-white border border-emerald-200 p-2.5 rounded-md text-xs space-y-1">
                <div className="flex items-center gap-1.5 text-emerald-700 font-medium truncate">
                  <FileCheck className="h-4 w-4 flex-shrink-0 text-emerald-600" />
                  <span className="truncate">{files.ledger.name}</span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-500">
                  <span>{(files.ledger.size / 1024).toFixed(1)} KB</span>
                  <button
                    type="button"
                    onClick={() => ledgerInputRef.current?.click()}
                    className="text-emerald-600 hover:underline font-medium cursor-pointer"
                  >
                    Replace
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => ledgerInputRef.current?.click()}
                className="w-full py-2.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-md text-xs font-medium text-slate-700 shadow-xs transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <Upload className="h-3.5 w-3.5 text-slate-400" />
                <span>ledger.csv</span>
              </button>
            )}
          </div>
        </div>

        {/* Bank Card */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => handleDrop('bank', e)}
          className={`border-2 border-dashed rounded-lg p-4 flex flex-col justify-between transition-colors bg-slate-50/50 ${
            files.bank ? 'border-emerald-400 bg-emerald-50/20' : 'border-slate-300 hover:border-slate-400'
          }`}
        >
          <div>
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="font-semibold text-slate-900">3. BANK</span>
              <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                Required
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mb-3">
              Settlements (`transaction_id`, `credited_amount`)
            </p>
          </div>

          <div>
            <input
              type="file"
              accept=".csv,text/csv"
              ref={bankInputRef}
              onChange={(e) => handleFileChange('bank', e)}
              className="hidden"
            />

            {files.bank ? (
              <div className="bg-white border border-emerald-200 p-2.5 rounded-md text-xs space-y-1">
                <div className="flex items-center gap-1.5 text-emerald-700 font-medium truncate">
                  <FileCheck className="h-4 w-4 flex-shrink-0 text-emerald-600" />
                  <span className="truncate">{files.bank.name}</span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-500">
                  <span>{(files.bank.size / 1024).toFixed(1)} KB</span>
                  <button
                    type="button"
                    onClick={() => bankInputRef.current?.click()}
                    className="text-emerald-600 hover:underline font-medium cursor-pointer"
                  >
                    Replace
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => bankInputRef.current?.click()}
                className="w-full py-2.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-md text-xs font-medium text-slate-700 shadow-xs transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <Upload className="h-3.5 w-3.5 text-slate-400" />
                <span>bank.csv</span>
              </button>
            )}
          </div>
        </div>

        {/* Adjustments Card */}
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => handleDrop('adjustments', e)}
          className={`border-2 border-dashed rounded-lg p-4 flex flex-col justify-between transition-colors bg-slate-50/50 ${
            files.adjustments ? 'border-emerald-400 bg-emerald-50/20' : 'border-slate-300 hover:border-slate-400'
          }`}
        >
          <div>
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="font-semibold text-slate-900">4. ADJUSTMENTS</span>
              <span className="text-[10px] font-medium text-slate-500 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded">
                Optional
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mb-3">
              Fee tickets (`transaction_id`, `adjustment_type`, `amount`)
            </p>
          </div>

          <div>
            <input
              type="file"
              accept=".csv,text/csv"
              ref={adjustmentsInputRef}
              onChange={(e) => handleFileChange('adjustments', e)}
              className="hidden"
            />

            {files.adjustments ? (
              <div className="bg-white border border-emerald-200 p-2.5 rounded-md text-xs space-y-1">
                <div className="flex items-center gap-1.5 text-emerald-700 font-medium truncate">
                  <FileCheck className="h-4 w-4 flex-shrink-0 text-emerald-600" />
                  <span className="truncate">{files.adjustments.name}</span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-500">
                  <span>{(files.adjustments.size / 1024).toFixed(1)} KB</span>
                  <button
                    type="button"
                    onClick={() => adjustmentsInputRef.current?.click()}
                    className="text-emerald-600 hover:underline font-medium cursor-pointer"
                  >
                    Replace
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => adjustmentsInputRef.current?.click()}
                className="w-full py-2.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-md text-xs font-medium text-slate-700 shadow-xs transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <Upload className="h-3.5 w-3.5 text-slate-400" />
                <span>adjustments.csv</span>
              </button>
            )}
          </div>
        </div>

      </div>

      {/* Dataset Validation Summary Banner */}
      {validationStatus && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-slate-900">Dataset Validation Summary</span>
            <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded ${
              validationStatus.valid
                ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                : 'bg-rose-100 text-rose-800 border border-rose-200'
            }`}>
              {validationStatus.valid ? '✓ Dataset Valid & Ready for Reconciliation' : '! Validation Errors Found'}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono pt-1">
            <div className="bg-white p-2 rounded border border-slate-200">
              <span className="text-slate-500 text-[11px] block">Payments</span>
              <span className="font-bold text-slate-900">
                {validationStatus.sources?.payments?.records ?? 0} records
              </span>
            </div>
            <div className="bg-white p-2 rounded border border-slate-200">
              <span className="text-slate-500 text-[11px] block">Ledger</span>
              <span className="font-bold text-slate-900">
                {validationStatus.sources?.ledger?.records ?? 0} records
              </span>
            </div>
            <div className="bg-white p-2 rounded border border-slate-200">
              <span className="text-slate-500 text-[11px] block">Bank</span>
              <span className="font-bold text-slate-900">
                {validationStatus.sources?.bank?.records ?? 0} records
              </span>
            </div>
            <div className="bg-white p-2 rounded border border-slate-200">
              <span className="text-slate-500 text-[11px] block">Adjustments</span>
              <span className="font-bold text-slate-900">
                {validationStatus.sources?.adjustments?.records ?? 0} records
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Target User Flow Action Row: [ Validate Dataset ] [ Run Reconciliation ] */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-slate-100">
        <div className="text-xs text-slate-500 flex items-center gap-1.5">
          <Info className="h-4 w-4 text-slate-400" />
          <span>Clicking <strong>Run Reconciliation</strong> automatically executes Phase 1 & parallel AI batch investigation.</span>
        </div>

        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          <button
            type="button"
            onClick={handleValidate}
            disabled={!allRequiredPresent || validating}
            className="px-4 py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50 cursor-pointer"
          >
            {validating ? 'Validating...' : 'Validate Dataset'}
          </button>

          <button
            type="button"
            onClick={onRunReconciliation}
            disabled={isRunning}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50 flex items-center gap-2 cursor-pointer"
          >
            <Play className="h-3.5 w-3.5 fill-current" />
            <span>{isRunning ? 'Reconciling...' : 'Run Reconciliation'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
