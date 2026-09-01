import React from 'react';

export default function KPICards({ metrics }) {
  if (!metrics) {
    return (
      <div className="bg-background border border-border rounded-lg p-6 text-center shadow-xs">
        <p className="text-sm font-semibold text-text">No reconciliation metrics available</p>
        <p className="text-xs text-text-secondary mt-1">
          Upload your data sources and run a reconciliation to see KPI summary metrics.
        </p>
      </div>
    );
  }

  const total = metrics.total_records ?? 0;
  const initialMatch = metrics.initial_reconciled ?? 0;
  const aiResolved = metrics.ai_auto_resolved ?? 0;
  const humanReview = metrics.human_review ?? 0;

  const matchPct = total > 0 ? ((initialMatch / total) * 100).toFixed(1) : '0.0';

  const cards = [
    {
      title: 'TOTAL RECORDS',
      value: total.toLocaleString(),
      subtext: 'Batch transactions',
      tag: 'Batch',
      tagColor: 'text-text-secondary bg-surface-alt border-border',
    },
    {
      title: 'INITIAL MATCH',
      value: initialMatch.toLocaleString(),
      subtext: `${matchPct}% of batch`,
      tag: 'Deterministic',
      tagColor: 'text-text bg-accent-green/10 border-accent-green/30',
    },
    {
      title: 'AI RESOLVED',
      value: aiResolved.toLocaleString(),
      subtext: 'Evidence-backed',
      tag: 'Proof Verified',
      tagColor: 'text-text bg-accent-green/10 border-accent-green/30',
    },
    {
      title: 'HUMAN REVIEW',
      value: humanReview.toLocaleString(),
      subtext: 'Requires attention',
      tag: 'Escalated',
      tagColor: 'text-text bg-accent-coral/10 border-accent-coral/30',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, idx) => (
        <div
          key={idx}
          className="bg-background border border-border rounded-lg p-5 flex flex-col justify-between shadow-xs hover:border-border transition-colors"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
              {card.title}
            </span>
            <span className={`text-[10px] font-mono font-medium px-2 py-0.5 rounded border ${card.tagColor}`}>
              {card.tag}
            </span>
          </div>

          <div className="mt-4">
            <div className="text-3xl font-semibold font-mono tracking-tight text-text">
              {card.value}
            </div>
            <p className="text-xs text-text-secondary mt-1 font-normal">{card.subtext}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
