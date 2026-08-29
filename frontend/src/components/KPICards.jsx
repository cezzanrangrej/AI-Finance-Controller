import React from 'react';

export default function KPICards({ metrics }) {
  if (!metrics) return null;

  const total = metrics.total_records || 100;
  const initialMatch = metrics.initial_reconciled || 70;
  const aiResolved = metrics.ai_auto_resolved ?? 8;
  const humanReview = metrics.human_review ?? 22;

  const matchPct = total > 0 ? ((initialMatch / total) * 100).toFixed(1) : '70.0';

  const cards = [
    {
      title: 'TOTAL RECORDS',
      value: total.toLocaleString(),
      subtext: 'Batch transactions',
      tag: 'Batch',
      tagColor: 'text-slate-600 bg-slate-100 border-slate-200',
    },
    {
      title: 'INITIAL MATCH',
      value: initialMatch.toLocaleString(),
      subtext: `${matchPct}% of batch`,
      tag: 'Deterministic',
      tagColor: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    },
    {
      title: 'AI RESOLVED',
      value: aiResolved.toLocaleString(),
      subtext: 'Evidence-backed',
      tag: 'Proof Verified',
      tagColor: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    },
    {
      title: 'HUMAN REVIEW',
      value: humanReview.toLocaleString(),
      subtext: 'Requires attention',
      tag: 'Escalated',
      tagColor: 'text-amber-700 bg-amber-50 border-amber-200',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, idx) => (
        <div
          key={idx}
          className="bg-white border border-slate-200 rounded-lg p-5 flex flex-col justify-between shadow-xs hover:border-slate-300 transition-colors"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              {card.title}
            </span>
            <span className={`text-[10px] font-mono font-medium px-2 py-0.5 rounded border ${card.tagColor}`}>
              {card.tag}
            </span>
          </div>

          <div className="mt-4">
            <div className="text-3xl font-semibold font-mono tracking-tight text-slate-900">
              {card.value}
            </div>
            <p className="text-xs text-slate-500 mt-1 font-normal">{card.subtext}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
