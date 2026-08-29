import React from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts';

export default function ExceptionChart({ breakdown }) {
  if (!breakdown || Object.keys(breakdown).length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg p-6 flex items-center justify-center h-64 text-slate-400 text-xs shadow-xs">
        No exception data available
      </div>
    );
  }

  const chartData = Object.entries(breakdown).map(([key, count]) => {
    const formattedName = key
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());

    const shortName = key
      .replace(/_RECORD|_ERROR/g, '')
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());

    return {
      rawKey: key,
      name: formattedName,
      shortName: shortName,
      count: count,
    };
  }).sort((a, b) => b.count - a.count);

  const totalExceptions = Object.values(breakdown).reduce((a, b) => a + b, 0);

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-6 flex flex-col justify-between shadow-xs">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Exception Breakdown
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Phase 1 rule violations by category
          </p>
        </div>
        <span className="text-xs font-mono font-medium text-slate-600 bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-md">
          {totalExceptions} exceptions
        </span>
      </div>

      {/* Bar Chart Visualization */}
      <div className="h-52 w-full my-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 25, left: 10, bottom: 5 }}>
            <XAxis
              type="number"
              stroke="#94a3b8"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}`}
            />
            <YAxis
              type="category"
              dataKey="shortName"
              stroke="#64748b"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              width={140}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                borderColor: '#1e293b',
                borderRadius: '8px',
                fontSize: '12px',
                color: '#ffffff',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              }}
              formatter={(value) => [`${value} cases`, 'Count']}
              labelStyle={{ color: '#ffffff', fontWeight: 600, marginBottom: '2px' }}
              cursor={{ fill: 'rgba(0, 0, 0, 0.03)' }}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={index === 0 ? '#10b981' : '#64748b'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Summary Matrix */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] pt-3 border-t border-slate-100">
        {chartData.map((item, idx) => (
          <div key={idx} className="flex items-center justify-between bg-slate-50 px-2.5 py-1.5 rounded border border-slate-200">
            <span className="text-slate-600 truncate mr-2">{item.shortName}</span>
            <span className="font-mono font-semibold text-slate-900">{item.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
