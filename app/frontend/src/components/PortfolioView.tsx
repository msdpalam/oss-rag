/**
 * PortfolioView — virtual portfolio tracker.
 * Lists all positions, shows cost basis, and allows add/remove.
 * Live P&L is computed by the agent tool (get_portfolio_summary);
 * this view manages the CRUD layer via REST.
 */
import { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2, RefreshCw, TrendingUp } from 'lucide-react';
import {
  listPositions,
  addPosition,
  deletePosition,
  type PortfolioPosition,
} from '../api/client';

const ASSET_TYPES = [
  { value: 'stock',      label: 'Stock' },
  { value: 'etf',        label: 'ETF' },
  { value: 'crypto_etf', label: 'Crypto ETF' },
  { value: 'crypto',     label: 'Crypto' },
];

export default function PortfolioView() {
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form state
  const [showForm, setShowForm] = useState(false);
  const [ticker, setTicker] = useState('');
  const [assetType, setAssetType] = useState('stock');
  const [shares, setShares] = useState('');
  const [avgCost, setAvgCost] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPositions(await listPositions());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load portfolio');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleAdd = async () => {
    if (!ticker.trim() || !shares || !avgCost) {
      setFormError('Ticker, shares, and avg cost are required.');
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      await addPosition({
        ticker: ticker.trim().toUpperCase(),
        asset_type: assetType,
        shares: parseFloat(shares),
        avg_cost_usd: parseFloat(avgCost),
        notes: notes.trim() || undefined,
      });
      setTicker(''); setShares(''); setAvgCost(''); setNotes('');
      setShowForm(false);
      await load();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to add position');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string, t: string) => {
    if (!confirm(`Remove ${t} from portfolio?`)) return;
    try {
      await deletePosition(id);
      setPositions((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove position');
    }
  };

  const totalCost = positions.reduce((s, p) => s + p.shares * p.avg_cost_usd, 0);

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-emerald-600" />
          </div>
          <div>
            <h1 className="font-semibold text-gray-900">Virtual Portfolio</h1>
            <p className="text-xs text-gray-500">
              {positions.length} position{positions.length !== 1 ? 's' : ''} · cost basis ${totalCost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => void load()}
            title="Refresh"
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => { setShowForm((s) => !s); setFormError(null); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Position
          </button>
        </div>
      </div>

      {/* Add Position form */}
      {showForm && (
        <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
          <p className="text-sm font-medium text-gray-700 mb-3">New Position</p>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Ticker *</label>
              <input
                type="text" placeholder="AAPL" value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Asset type</label>
              <select
                value={assetType}
                onChange={(e) => setAssetType(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                {ASSET_TYPES.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Shares *</label>
              <input
                type="number" min="0" step="any" placeholder="10"
                value={shares} onChange={(e) => setShares(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Avg cost (USD) *</label>
              <input
                type="number" min="0" step="any" placeholder="150.00"
                value={avgCost} onChange={(e) => setAvgCost(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
          </div>
          <div className="mb-3">
            <label className="text-xs text-gray-500 block mb-1">Notes (optional)</label>
            <input
              type="text" placeholder="e.g. Long-term hold"
              value={notes} onChange={(e) => setNotes(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          {formError && <p className="text-xs text-red-600 mb-2">{formError}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => void handleAdd()}
              disabled={saving}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
            >
              {saving ? 'Adding…' : 'Add'}
            </button>
            <button
              onClick={() => { setShowForm(false); setFormError(null); }}
              className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Position list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="px-6 py-4 text-sm text-red-600">{error}</div>
        ) : positions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 py-16">
            <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center mb-4">
              <TrendingUp className="w-7 h-7 text-emerald-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-800 mb-2">No positions yet</h2>
            <p className="text-sm text-gray-500 max-w-xs">
              Add your holdings to track P&L and let Casey (Portfolio Strategist) analyse your allocation.
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-xs text-gray-500 font-medium">
                <th className="text-left px-6 py-3">Ticker</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-right px-4 py-3">Shares</th>
                <th className="text-right px-4 py-3">Avg Cost</th>
                <th className="text-right px-6 py-3">Cost Basis</th>
                <th className="text-right px-6 py-3">Notes</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                  <td className="px-6 py-3 font-semibold text-gray-900">{p.ticker}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{p.asset_type}</td>
                  <td className="px-4 py-3 text-right text-gray-700">{p.shares.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  <td className="px-4 py-3 text-right text-gray-700">${p.avg_cost_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                  <td className="px-6 py-3 text-right text-gray-900 font-medium">
                    ${(p.shares * p.avg_cost_usd).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </td>
                  <td className="px-6 py-3 text-right text-gray-400 text-xs max-w-[120px] truncate">{p.notes ?? ''}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => void handleDelete(p.id, p.ticker)}
                      title="Remove position"
                      className="p-1 rounded text-gray-300 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer note */}
      {positions.length > 0 && (
        <div className="px-6 py-3 border-t border-gray-100 text-xs text-gray-400">
          Ask Casey (Portfolio Strategist) to run <em>get_portfolio_summary</em> for live P&L and rebalancing suggestions.
        </div>
      )}
    </div>
  );
}
