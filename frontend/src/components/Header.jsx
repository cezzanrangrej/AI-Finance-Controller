import React from 'react';
import { ShieldCheck, Play, RefreshCw, Layers, Cpu } from 'lucide-react';

export default function Header({ onRun, isRunning, activeRunId, runs, onSelectRun }) {
  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
        
        {/* Title and Badge */}
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <ShieldCheck className="h-6 w-6 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-white tracking-tight">AI FINANCE CONTROLLER</h1>
              <span className="px-2 py-0.5 text-xs font-mono font-medium rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Gemini Multi-Agent
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium">Multi-Source Financial Reconciliation & AI Exception Investigation</p>
          </div>
        </div>

        {/* Actions & Run Selector */}
        <div className="flex items-center gap-3">
          {/* Run selector dropdown */}
          {runs && runs.length > 0 && (
            <div className="flex items-center gap-2 bg-slate-800/80 border border-slate-700/60 rounded-lg px-3 py-1.5 text-xs">
              <Layers className="h-3.5 w-3.5 text-slate-400" />
              <select
                value={activeRunId || ''}
                onChange={(e) => onSelectRun(e.target.value)}
                className="bg-transparent text-slate-200 font-mono font-medium outline-none cursor-pointer"
              >
                {runs.map((r) => (
                  <option key={r.run_id} value={r.run_id} className="bg-slate-900 text-slate-200">
                    {r.run_id} ({new Date(r.created_at).toLocaleTimeString()})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Trigger Run Button */}
          <button
            onClick={onRun}
            disabled={isRunning}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold tracking-wide transition-all shadow-md ${
              isRunning
                ? 'bg-slate-800 text-slate-400 cursor-not-allowed border border-slate-700'
                : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/25 active:scale-95'
            }`}
          >
            {isRunning ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin text-indigo-400" />
                <span>RUNNING RECONCILIATION...</span>
              </>
            ) : (
              <>
                <Play className="h-4 w-4 fill-current" />
                <span>RUN RECONCILIATION</span>
              </>
            )}
          </button>
        </div>

      </div>
    </header>
  );
}
