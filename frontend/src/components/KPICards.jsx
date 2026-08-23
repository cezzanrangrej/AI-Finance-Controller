import React from 'react';
import { Database, CheckCircle2, Bot, AlertTriangle } from 'lucide-react';

export default function KPICards({ metrics }) {
  if (!metrics) return null;

  const total = metrics.total_records || 100;
  const initialMatch = metrics.initial_reconciled || 70;
  const aiResolved = metrics.ai_auto_resolved ?? 8;
  const humanReview = metrics.human_review ?? 22;

  const cards = [
    {
      title: 'Total Records',
      value: total,
      label: 'Batch Transactions',
      icon: Database,
      color: 'text-slate-200',
      bg: 'bg-slate-900/90 border-slate-800',
      iconBg: 'bg-slate-800 text-slate-400',
    },
    {
      title: 'Initial Match',
      value: initialMatch,
      label: 'Phase 1 Deterministic',
      icon: CheckCircle2,
      color: 'text-emerald-400',
      bg: 'bg-emerald-950/20 border-emerald-900/40',
      iconBg: 'bg-emerald-500/10 text-emerald-400',
    },
    {
      title: 'AI Resolved',
      value: aiResolved,
      label: 'Evidence-backed Resolution',
      icon: Bot,
      color: 'text-indigo-400',
      bg: 'bg-indigo-950/20 border-indigo-900/40',
      iconBg: 'bg-indigo-500/10 text-indigo-400',
    },
    {
      title: 'Human Review',
      value: humanReview,
      label: 'Unresolved Discrepancies',
      icon: AlertTriangle,
      color: 'text-amber-400',
      bg: 'bg-amber-950/20 border-amber-900/40',
      iconBg: 'bg-amber-500/10 text-amber-400',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className={`p-5 rounded-2xl border ${card.bg} shadow-sm backdrop-blur-sm flex flex-col justify-between transition-all hover:scale-[1.01]`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                {card.title}
              </span>
              <div className={`p-2 rounded-xl ${card.iconBg}`}>
                <Icon className="h-5 w-5" />
              </div>
            </div>
            <div className="mt-4">
              <div className={`text-3xl font-extrabold font-mono tracking-tight ${card.color}`}>
                {card.value}
              </div>
              <p className="text-xs text-slate-400 mt-1 font-medium">{card.label}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
