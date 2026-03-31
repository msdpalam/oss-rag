import { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

type Tab = 'login' | 'signup';

export default function AuthPage() {
  const { login, register } = useAuth();
  const [tab, setTab] = useState<Tab>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (tab === 'login') {
        await login(email, password);
      } else {
        await register(email, password, displayName || undefined);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center">
            <MessageSquare className="w-5 h-5 text-white" />
          </div>
          <span className="text-white text-xl font-semibold">OSS RAG Chat</span>
        </div>

        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          {/* Tabs */}
          <div className="flex rounded-lg bg-gray-800 p-1 mb-6">
            {(['login', 'signup'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setError(''); }}
                className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors
                  ${tab === t
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-400 hover:text-gray-200'
                  }`}
              >
                {t === 'login' ? 'Sign in' : 'Create account'}
              </button>
            ))}
          </div>

          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
            {tab === 'signup' && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">Display name (optional)</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-white text-sm placeholder-gray-500
                             focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
            )}

            <div>
              <label className="block text-sm text-gray-400 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                           text-white text-sm placeholder-gray-500
                           focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                placeholder="••••••••"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                           text-white text-sm placeholder-gray-500
                           focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              {tab === 'signup' && (
                <p className="text-xs text-gray-500 mt-1">Minimum 8 characters</p>
              )}
            </div>

            {error && (
              <p className="text-sm text-red-400 bg-red-950/40 border border-red-800/50 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60
                         disabled:cursor-not-allowed text-white font-medium py-2 rounded-lg
                         text-sm transition-colors"
            >
              {loading
                ? (tab === 'login' ? 'Signing in…' : 'Creating account…')
                : (tab === 'login' ? 'Sign in' : 'Create account')
              }
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
