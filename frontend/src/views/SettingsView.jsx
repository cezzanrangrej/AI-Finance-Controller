import React from 'react';
import { Settings, Shield, Cpu, Database, CheckCircle2, Sliders, Layers, Zap } from 'lucide-react';

export default function SettingsView({ settings, onUpdateSettings, metrics }) {
  const handleChange = (key, value) => {
    if (onUpdateSettings) {
      onUpdateSettings({ ...settings, [key]: value });
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-background rounded-lg border border-border shadow-xs p-6 space-y-6">
        <div className="pb-4 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-text">Advanced AI & Developer Configuration</h2>
            <p className="text-xs text-text-secondary mt-0.5">
              Configure internal execution parameters, LLM providers, batch sizes, and benchmark modes.
            </p>
          </div>
          <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-surface-alt text-text-secondary border border-border font-semibold self-start sm:self-auto">
            Developer / Benchmark Controls
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Section 1: Developer AI Parameters */}
          <div className="bg-surface border border-border rounded-lg p-5 space-y-4">
            <div className="flex items-center gap-2 text-text font-semibold text-xs pb-2 border-b border-border">
              <Sliders className="h-4 w-4 text-accent-purple" />
              <span>Execution Engine Settings</span>
            </div>

            {/* Provider Selector */}
            <div className="space-y-1 text-xs">
              <label className="text-text-secondary font-medium block">LLM Provider</label>
              <select
                value={settings?.provider || 'gemini'}
                onChange={(e) => handleChange('provider', e.target.value)}
                className="w-full bg-background border border-border rounded-md px-3 py-1.5 text-xs text-text outline-none focus:border-primary font-mono"
              >
                <option value="gemini">Gemini API (Default)</option>
                <option value="demo">Demo Mode (Offline Fast)</option>
                <option value="openrouter">OpenRouter</option>
              </select>
            </div>

            {/* Unified Architecture Indicator */}
            <div className="space-y-1 text-xs">
              <label className="text-text-secondary font-medium block">Investigation Architecture</label>
              <div className="w-full bg-background border border-border rounded-md px-3 py-1.5 text-xs text-text font-mono flex items-center justify-between">
                <span>Parallel Batch Multi-Agent</span>
                <span className="text-[10px] text-accent-purple bg-accent-purple/10 border border-accent-purple/30 px-1.5 py-0.5 rounded font-semibold">Unified</span>
              </div>
            </div>

            {/* Batch Size Selector */}
            <div className="space-y-1 text-xs">
              <label className="text-text-secondary font-medium block">Batch Size (Internal Ceiling: 10)</label>
              <select
                value={settings?.batchSize || 5}
                onChange={(e) => handleChange('batchSize', Number(e.target.value))}
                className="w-full bg-background border border-border rounded-md px-3 py-1.5 text-xs text-text outline-none focus:border-primary font-mono"
              >
                <option value={2}>2 cases / batch</option>
                <option value={3}>3 cases / batch</option>
                <option value={4}>4 cases / batch</option>
                <option value={5}>5 cases / batch (Default)</option>
                <option value={8}>8 cases / batch</option>
                <option value={10}>10 cases / batch (Max Ceiling)</option>
              </select>
            </div>

            {/* Internal Safety Parameters */}
            <div className="pt-2 border-t border-border space-y-1.5 text-[11px] font-mono text-text-secondary">
              <div className="flex justify-between">
                <span className="text-text-secondary/60">Max Concurrency Ceiling:</span>
                <span className="font-bold text-text">5 parallel slots</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary/60">Partition Strategy:</span>
                <span className="font-bold text-text">balanced_exception_type</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary/60">Max Safety Tool Calls:</span>
                <span className="font-bold text-text">5 per case</span>
              </div>
            </div>
          </div>

          {/* Section 2: Deterministic Rules Reference */}
          <div className="bg-surface border border-border rounded-lg p-5 space-y-3">
            <div className="flex items-center gap-2 text-text font-semibold text-xs pb-2 border-b border-border">
              <Shield className="h-4 w-4 text-primary" />
              <span>Phase 1 Deterministic Rule Engine</span>
            </div>
            <ul className="text-xs space-y-2 text-text-secondary">
              <li className="flex items-center gap-2 bg-background p-2 rounded border border-border">
                <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
                <div>
                  <span className="font-semibold text-text block">MISSING_LEDGER_RECORD</span>
                  <span className="text-[11px] text-text-secondary">Payment captured, missing ERP ledger entry.</span>
                </div>
              </li>
              <li className="flex items-center gap-2 bg-background p-2 rounded border border-border">
                <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
                <div>
                  <span className="font-semibold text-text block">GROSS_AMOUNT_MISMATCH</span>
                  <span className="text-[11px] text-text-secondary">Gateway payment does not match ledger gross amount.</span>
                </div>
              </li>
              <li className="flex items-center gap-2 bg-background p-2 rounded border border-border">
                <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
                <div>
                  <span className="font-semibold text-text block">LEDGER_CALCULATION_ERROR</span>
                  <span className="text-[11px] text-text-secondary">Ledger net amount differs from gross - fee.</span>
                </div>
              </li>
              <li className="flex items-center gap-2 bg-background p-2 rounded border border-border">
                <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
                <div>
                  <span className="font-semibold text-text block">MISSING_BANK_RECORD</span>
                  <span className="text-[11px] text-text-secondary">Ledger record posted, missing bank credit statement.</span>
                </div>
              </li>
              <li className="flex items-center gap-2 bg-background p-2 rounded border border-border">
                <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
                <div>
                  <span className="font-semibold text-text block">DUPLICATE_BANK_RECORD</span>
                  <span className="text-[11px] text-text-secondary">Multiple bank settlement records for transaction.</span>
                </div>
              </li>
              <li className="flex items-center gap-2 bg-background p-2 rounded border border-border">
                <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
                <div>
                  <span className="font-semibold text-text block">BANK_AMOUNT_MISMATCH</span>
                  <span className="text-[11px] text-text-secondary">Settled bank amount differs from expected net ledger.</span>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
