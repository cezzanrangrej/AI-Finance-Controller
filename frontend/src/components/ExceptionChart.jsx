import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis } from 'recharts';
import { BarChart3 } from 'lucide-react';

export default function ExceptionChart({ breakdown }) {
  if (!breakdown || Object.keys(breakdown).length === 0) {
    return (
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-sm flex items-center justify-center h-64 text-slate-500 text-xs">
        No exception data available
      </div>
    );
  }

  const COLORS = {
    GROSS_AMOUNT_MISMATCH: '#f59e0b',
    MISSING_LEDGER_RECORD: '#ef4444',
    MISSING_BANK_RECORD: '#f97316',
    BANK_AMOUNT_MISMATCH: '#8b5cf6',
    DUPLICATE_BANK_RECORD: '#ec4899',
    LEDGER_CALCULATION_ERROR: '#3b82f6',
  };

  const chartData = Object.entries(breakdown).map(([key, count]) => ({
    name: key.replace(/_/g, ' '),
    shortName: key.replace(/_RECORD|_ERROR/g, '').replace(/_/g, ' '),
    count: count,
    color: COLORS[key] || '#64748b',
  })).sort((a, b) => b.count - a.count);

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-sm backdrop-blur-sm flex flex-col justify-between">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-amber-400" />
          <h2 className="text-base font-bold text-slate-100">Exception Category Breakdown</h2>
        </div>
        <span className="text-xs text-slate-400 font-mono font-medium">
          {Object.values(breakdown).reduce((a, b) => a + b, 0)} Total Exceptions
        </span>
      </div>

      <div className="h-56 w-full my-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <XAxis type="number" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="shortName" stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} width={130} />
            <Tooltip
              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '12px', fontSize: '12px' }}
              itemStyle={{ color: '#f8fafc' }}
              cursor={{ fill: 'rgba(255, 255, 255, 0.05)' }}
            />
            <Bar dataKey="count" radius={[0, 8, 8, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px] pt-3 border-t border-slate-800/80">
        {chartData.map((item, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />
            <span className="text-slate-400 truncate">{item.name}:</span>
            <span className="font-mono font-bold text-slate-200 ml-auto">{item.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
