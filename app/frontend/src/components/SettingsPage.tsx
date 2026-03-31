/**
 * SettingsPage — investor profile editor.
 * Opens as a full overlay from the gear icon in the sidebar.
 * Loads existing profile on mount; saves via PUT /profile.
 */
import { useEffect, useState } from 'react';
import { X, Save, User } from 'lucide-react';
import { getProfile, updateProfile } from '../api/client';
import type { InvestorProfile } from '../types';

interface Props {
  onClose: () => void;
}

const RISK_LABELS: Record<number, string> = {
  1: 'Very Conservative',
  2: 'Conservative',
  3: 'Moderate',
  4: 'Growth',
  5: 'Aggressive',
};

const RISK_COLORS: Record<number, string> = {
  1: 'bg-green-50 border-green-300 text-green-700',
  2: 'bg-teal-50 border-teal-300 text-teal-700',
  3: 'bg-blue-50 border-blue-300 text-blue-700',
  4: 'bg-orange-50 border-orange-300 text-orange-700',
  5: 'bg-red-50 border-red-300 text-red-700',
};

const GOALS = [
  { value: 'retirement', label: 'Retirement' },
  { value: 'growth',     label: 'Growth' },
  { value: 'income',     label: 'Income' },
  { value: 'preservation', label: 'Capital Preservation' },
];

const TAX_ACCOUNTS = [
  { value: '401k',           label: '401(k)' },
  { value: 'roth_ira',       label: 'Roth IRA' },
  { value: 'traditional_ira', label: 'Traditional IRA' },
  { value: 'taxable',        label: 'Taxable Brokerage' },
];

export default function SettingsPage({ onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveOk, setSaveOk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [age, setAge] = useState<number>(35);
  const [riskTolerance, setRiskTolerance] = useState<number>(3);
  const [horizonYears, setHorizonYears] = useState<number>(20);
  const [goals, setGoals] = useState<string[]>([]);
  const [portfolioSize, setPortfolioSize] = useState<string>('');
  const [monthlyContrib, setMonthlyContrib] = useState<string>('');
  const [taxAccounts, setTaxAccounts] = useState<string[]>([]);

  useEffect(() => {
    getProfile()
      .then((p: InvestorProfile) => {
        if (p.age) setAge(p.age);
        if (p.risk_tolerance) setRiskTolerance(p.risk_tolerance);
        if (p.horizon_years) setHorizonYears(p.horizon_years);
        if (p.goals?.length) setGoals(p.goals);
        if (p.portfolio_size_usd) setPortfolioSize(String(p.portfolio_size_usd));
        if (p.monthly_contribution_usd) setMonthlyContrib(String(p.monthly_contribution_usd));
        if (p.tax_accounts?.length) setTaxAccounts(p.tax_accounts);
      })
      .catch(() => { /* no profile yet — keep defaults */ })
      .finally(() => setLoading(false));
  }, []);

  const toggleGoal = (v: string) =>
    setGoals((prev) => prev.includes(v) ? prev.filter((g) => g !== v) : [...prev, v]);

  const toggleTax = (v: string) =>
    setTaxAccounts((prev) => prev.includes(v) ? prev.filter((t) => t !== v) : [...prev, v]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaveOk(false);
    try {
      await updateProfile({
        age,
        risk_tolerance: riskTolerance,
        horizon_years: horizonYears,
        goals,
        portfolio_size_usd: portfolioSize ? parseInt(portfolioSize.replace(/,/g, ''), 10) : undefined,
        monthly_contribution_usd: monthlyContrib ? parseInt(monthlyContrib.replace(/,/g, ''), 10) : undefined,
        tax_accounts: taxAccounts,
      });
      setSaveOk(true);
      setTimeout(() => setSaveOk(false), 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-100">
          <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
            <User className="w-4 h-4 text-indigo-600" />
          </div>
          <div className="flex-1">
            <h2 className="font-semibold text-gray-900">Investor Profile</h2>
            <p className="text-xs text-gray-500">Personalise analyst recommendations to your situation</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-12">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">

            {/* Age */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-sm font-medium text-gray-700">Age</label>
                <span className="text-sm font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">{age}</span>
              </div>
              <input
                type="range" min={18} max={80} value={age}
                onChange={(e) => setAge(Number(e.target.value))}
                className="w-full accent-indigo-600"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>18</span><span>80</span>
              </div>
            </div>

            {/* Risk tolerance */}
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">Risk Tolerance</label>
              <div className="grid grid-cols-5 gap-1.5">
                {[1, 2, 3, 4, 5].map((v) => (
                  <button
                    key={v}
                    onClick={() => setRiskTolerance(v)}
                    className={`py-2 px-1 rounded-lg border text-xs font-medium transition-all text-center
                                ${riskTolerance === v
                                  ? RISK_COLORS[v] + ' border-2'
                                  : 'bg-gray-50 border-gray-200 text-gray-500 hover:border-gray-300'}`}
                  >
                    {RISK_LABELS[v]}
                  </button>
                ))}
              </div>
            </div>

            {/* Goals */}
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">Investment Goals</label>
              <div className="grid grid-cols-2 gap-2">
                {GOALS.map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => toggleGoal(value)}
                    className={`py-2.5 px-3 rounded-lg border text-sm transition-all text-left
                                ${goals.includes(value)
                                  ? 'bg-indigo-50 border-indigo-300 text-indigo-700 font-medium'
                                  : 'bg-gray-50 border-gray-200 text-gray-600 hover:border-gray-300'}`}
                  >
                    {goals.includes(value) ? '✓ ' : ''}{label}
                  </button>
                ))}
              </div>
            </div>

            {/* Horizon */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-sm font-medium text-gray-700">Investment Horizon</label>
                <span className="text-sm font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
                  {horizonYears} yr{horizonYears !== 1 ? 's' : ''}
                </span>
              </div>
              <input
                type="range" min={1} max={40} value={horizonYears}
                onChange={(e) => setHorizonYears(Number(e.target.value))}
                className="w-full accent-indigo-600"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>1 yr</span><span>40 yrs</span>
              </div>
            </div>

            {/* Portfolio size + monthly contribution */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1.5">Portfolio Size ($)</label>
                <input
                  type="number" min={0} placeholder="e.g. 50000"
                  value={portfolioSize}
                  onChange={(e) => setPortfolioSize(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1.5">Monthly Contribution ($)</label>
                <input
                  type="number" min={0} placeholder="e.g. 500"
                  value={monthlyContrib}
                  onChange={(e) => setMonthlyContrib(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
            </div>

            {/* Tax accounts */}
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">Tax-Advantaged Accounts</label>
              <div className="grid grid-cols-2 gap-2">
                {TAX_ACCOUNTS.map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => toggleTax(value)}
                    className={`py-2.5 px-3 rounded-lg border text-sm transition-all text-left
                                ${taxAccounts.includes(value)
                                  ? 'bg-indigo-50 border-indigo-300 text-indigo-700 font-medium'
                                  : 'bg-gray-50 border-gray-200 text-gray-600 hover:border-gray-300'}`}
                  >
                    {taxAccounts.includes(value) ? '✓ ' : ''}{label}
                  </button>
                ))}
              </div>
            </div>

          </div>
        )}

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex items-center gap-3">
          {error && <p className="text-xs text-red-600 flex-1">{error}</p>}
          {saveOk && <p className="text-xs text-green-600 flex-1">Profile saved!</p>}
          {!error && !saveOk && <div className="flex-1" />}
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSave()}
            disabled={saving || loading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Saving…' : 'Save Profile'}
          </button>
        </div>
      </div>
    </div>
  );
}
