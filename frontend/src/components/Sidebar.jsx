import React from 'react';
import {
  LayoutDashboard,
  Layers,
  Database,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Settings,
  Shield,
  PanelLeftClose,
} from 'lucide-react';

export default function Sidebar({ activeTab, onSelectTab, isOpen, onToggleSidebar }) {
  const navItems = [
    { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { key: 'runs', label: 'Runs', icon: Layers },
    { key: 'datasources', label: 'Data Sources', icon: Database },
    { key: 'exceptions', label: 'Exceptions', icon: AlertTriangle },
    { key: 'evaluations', label: 'Evaluations', icon: CheckCircle2 },
    { key: 'audit', label: 'Audit Log', icon: FileText },
    { key: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-40 lg:hidden"
          onClick={onToggleSidebar}
        />
      )}

      {/* Sticky, In-Flow Sidebar for Desktop + Responsive Drawer */}
      <aside
        className={`fixed lg:sticky top-0 left-0 h-screen z-50 lg:z-30 w-64 bg-[#111827] text-slate-300 flex flex-col border-r border-[#1F2937] flex-shrink-0 transition-all duration-200 ease-in-out ${
          isOpen ? 'translate-x-0 lg:ml-0' : '-translate-x-full lg:-ml-64'
        }`}
      >
        {/* Brand Header + Close Button */}
        <div className="h-16 px-4 flex items-center justify-between border-b border-[#1F2937] bg-[#0E1522]">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center text-primary-light flex-shrink-0">
              <Shield className="h-5 w-5" strokeWidth={2.2} />
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
                ReconPilot
              </div>
              <div className="text-[10px] text-slate-400 font-normal">
                Reconciliation Platform
              </div>
            </div>
          </div>

          {/* Close Sidebar Button */}
          <button
            onClick={onToggleSidebar}
            title="Close / Hide Sidebar"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#1F2937] transition-colors cursor-pointer"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        {/* Navigation items */}
        <div className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
          <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Navigation
          </div>

          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.key;
            return (
              <button
                key={item.key}
                onClick={() => {
                  onSelectTab(item.key);
                }}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-primary/15 text-primary-light font-semibold border-l-3 border-primary-light'
                    : 'text-slate-400 hover:text-white hover:bg-[#1F2937]'
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? 'text-primary-light' : 'text-slate-400'}`} />
                <span>{item.label}</span>
                {item.key === 'datasources' && (
                  <span className="ml-auto text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                    CSV
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* System Health / Engine Status */}
        <div className="p-4 border-t border-[#1F2937] bg-[#0E1522] text-xs">
          <div className="flex items-center justify-between text-slate-400 mb-1.5">
            <span className="text-[11px] font-semibold text-slate-300">System Status</span>
            <div className="flex items-center gap-1.5 text-[11px] text-primary-light font-medium">
              <span className="h-1.5 w-1.5 rounded-full bg-primary-light animate-pulse" />
              Operational
            </div>
          </div>
          <div className="text-[10px] text-slate-500 font-mono">
            Engine: Phase 3.1 · SQLite DB
          </div>
        </div>
      </aside>
    </>
  );
}
