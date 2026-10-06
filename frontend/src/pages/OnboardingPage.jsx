import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { platformApi } from '../services/api';
import {
  Sparkles,
  Flame,
  Code,
  Database,
  ArrowRight,
  CheckCircle,
  AlertCircle,
  Link as LinkIcon,
  ShieldCheck,
} from 'lucide-react';

const OnboardingPage = ({ onComplete }) => {
  const { user } = useAuth();

  const [cfHandle, setCfHandle] = useState('');
  const [cfApiKey, setCfApiKey] = useState('');
  const [cfApiSecret, setCfApiSecret] = useState('');
  const [lcHandle, setLcHandle] = useState('');
  const [ccHandle, setCcHandle] = useState('');

  const [connectedProfiles, setConnectedProfiles] = useState({});
  const [connectingPlatform, setConnectingPlatform] = useState(null);
  const [errorMap, setErrorMap] = useState({});

  // Fetch current platform statuses on mount
  const fetchStatuses = async () => {
    try {
      const statuses = await platformApi.getAllStatuses();
      const map = {};
      statuses.forEach((s) => {
        map[s.platform] = s.handle;
      });
      setConnectedProfiles(map);
      if (map.codeforces) setCfHandle(map.codeforces);
      if (map.leetcode) setLcHandle(map.leetcode);
      if (map.codechef) setCcHandle(map.codechef);
    } catch (err) {
      console.error('Failed to fetch platform status during onboarding:', err);
    }
  };

  useEffect(() => {
    fetchStatuses();
  }, []);

  const handleConnect = async (platform) => {
    setConnectingPlatform(platform);
    setErrorMap((prev) => ({ ...prev, [platform]: '' }));

    try {
      if (platform === 'codeforces') {
        if (!cfHandle.trim()) return;
        const res = await platformApi.connectCodeforces(
          cfHandle.trim(),
          cfApiKey.trim() || null,
          cfApiSecret.trim() || null
        );
        setConnectedProfiles((prev) => ({ ...prev, codeforces: res.handle }));
      } else if (platform === 'leetcode') {
        if (!lcHandle.trim()) return;
        const res = await platformApi.connectLeetCode(lcHandle.trim());
        setConnectedProfiles((prev) => ({ ...prev, leetcode: res.handle }));
      } else if (platform === 'codechef') {
        if (!ccHandle.trim()) return;
        const res = await platformApi.connectCodeChef(ccHandle.trim());
        setConnectedProfiles((prev) => ({ ...prev, codechef: res.handle }));
      }
    } catch (err) {
      let msg = err.response?.data?.detail;
      if (Array.isArray(msg)) {
        msg = msg.map((m) => m.msg || m.message || JSON.stringify(m)).join(', ');
      } else if (typeof msg === 'object' && msg !== null) {
        msg = msg.message || JSON.stringify(msg);
      }
      if (!msg) {
        msg = err.message || `Failed to connect ${platform} profile.`;
      }
      setErrorMap((prev) => ({ ...prev, [platform]: msg }));
    } finally {
      setConnectingPlatform(null);
    }
  };

  return (
    <div style={styles.overlay}>
      <div className="glass-panel" style={styles.card}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.iconCircle}>
            <Sparkles size={28} color="#6366f1" />
          </div>
          <div>
            <h1 style={styles.title}>Connect Your Coding Profiles</h1>
            <p style={styles.subtitle}>These should be YOUR usernames.</p>
          </div>
        </div>

        <div style={styles.bannerNote}>
          <ShieldCheck size={18} color="#34d399" />
          <span>
            Connect any profile now. Profiles validate independently. Click <strong>Continue</strong> when ready.
          </span>
        </div>

        {/* Connected Summary */}
        {(connectedProfiles.codeforces || connectedProfiles.leetcode || connectedProfiles.codechef) && (
          <div style={styles.myProfilesSummary}>
            <span style={styles.summaryTitle}>MY PROFILES</span>
            {connectedProfiles.codeforces && (
              <div style={styles.summaryRow}>
                <span>Codeforces → <strong>{connectedProfiles.codeforces}</strong></span>
                <span style={styles.connectedBadge}><CheckCircle size={14} /> Connected</span>
              </div>
            )}
            {connectedProfiles.leetcode && (
              <div style={styles.summaryRow}>
                <span>LeetCode → <strong>{connectedProfiles.leetcode}</strong></span>
                <span style={styles.connectedBadge}><CheckCircle size={14} /> Connected</span>
              </div>
            )}
            {connectedProfiles.codechef && (
              <div style={styles.summaryRow}>
                <span>CodeChef → <strong>{connectedProfiles.codechef}</strong></span>
                <span style={styles.connectedBadge}><CheckCircle size={14} /> Connected</span>
              </div>
            )}
          </div>
        )}

        {/* Form Fields */}
        <div style={styles.form}>
          {/* Codeforces */}
          <div style={styles.fieldGroup}>
            <div style={styles.fieldLabelRow}>
              <Flame size={16} color="#f59e0b" />
              <span style={styles.fieldTitle}>Codeforces</span>
            </div>
            <div style={styles.inputRow}>
              <input
                type="text"
                placeholder="Codeforces handle (e.g. Jyoascoder)"
                value={cfHandle}
                onChange={(e) => setCfHandle(e.target.value)}
                className="input-field"
                style={{ flex: 1 }}
              />
              <button
                type="button"
                onClick={() => handleConnect('codeforces')}
                disabled={connectingPlatform === 'codeforces' || !cfHandle.trim()}
                className="btn-secondary"
                style={{ minWidth: '95px' }}
              >
                {connectingPlatform === 'codeforces' ? 'Validating...' : 'Connect'}
              </button>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.2rem' }}>
              <input
                type="text"
                placeholder="Optional API Key"
                value={cfApiKey}
                onChange={(e) => setCfApiKey(e.target.value)}
                className="input-field"
                style={{ fontSize: '0.78rem' }}
              />
              <input
                type="password"
                placeholder="Optional API Secret"
                value={cfApiSecret}
                onChange={(e) => setCfApiSecret(e.target.value)}
                className="input-field"
                style={{ fontSize: '0.78rem' }}
              />
            </div>
            {errorMap.codeforces && (
              <div style={styles.errorText}>
                <AlertCircle size={14} /> <span>{errorMap.codeforces}</span>
              </div>
            )}
          </div>

          {/* LeetCode */}
          <div style={styles.fieldGroup}>
            <div style={styles.fieldLabelRow}>
              <Code size={16} color="#fbbf24" />
              <span style={styles.fieldTitle}>LeetCode</span>
            </div>
            <div style={styles.inputRow}>
              <input
                type="text"
                placeholder="LeetCode username (e.g. Pragnya)"
                value={lcHandle}
                onChange={(e) => setLcHandle(e.target.value)}
                className="input-field"
                style={{ flex: 1 }}
              />
              <button
                type="button"
                onClick={() => handleConnect('leetcode')}
                disabled={connectingPlatform === 'leetcode' || !lcHandle.trim()}
                className="btn-secondary"
                style={{ minWidth: '95px' }}
              >
                {connectingPlatform === 'leetcode' ? 'Validating...' : 'Connect'}
              </button>
            </div>
            {errorMap.leetcode && (
              <div style={styles.errorText}>
                <AlertCircle size={14} /> <span>{errorMap.leetcode}</span>
              </div>
            )}
          </div>

          {/* CodeChef */}
          <div style={styles.fieldGroup}>
            <div style={styles.fieldLabelRow}>
              <Database size={16} color="#34d399" />
              <span style={styles.fieldTitle}>CodeChef</span>
            </div>
            <div style={styles.inputRow}>
              <input
                type="text"
                placeholder="CodeChef username (e.g. chef_user)"
                value={ccHandle}
                onChange={(e) => setCcHandle(e.target.value)}
                className="input-field"
                style={{ flex: 1 }}
              />
              <button
                type="button"
                onClick={() => handleConnect('codechef')}
                disabled={connectingPlatform === 'codechef' || !ccHandle.trim()}
                className="btn-secondary"
                style={{ minWidth: '95px' }}
              >
                {connectingPlatform === 'codechef' ? 'Validating...' : 'Connect'}
              </button>
            </div>
            {errorMap.codechef && (
              <div style={styles.errorText}>
                <AlertCircle size={14} /> <span>{errorMap.codechef}</span>
              </div>
            )}
          </div>

          {/* Actions */}
          <div style={styles.actions}>
            <button
              type="button"
              onClick={onComplete}
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center', padding: '0.75rem' }}
            >
              <span>Continue</span>
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const styles = {
  overlay: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#0b0f19',
    padding: '2rem 1rem',
  },
  card: {
    width: '100%',
    maxWidth: '560px',
    padding: '2rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1.4rem',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
  },
  iconCircle: {
    width: '52px',
    height: '52px',
    borderRadius: '14px',
    background: 'rgba(99, 102, 241, 0.15)',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  title: {
    fontSize: '1.4rem',
    fontWeight: '800',
    color: '#f9fafb',
  },
  subtitle: {
    fontSize: '0.85rem',
    color: '#9ca3af',
    marginTop: '0.2rem',
  },
  bannerNote: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    background: 'rgba(52, 211, 153, 0.1)',
    border: '1px solid rgba(52, 211, 153, 0.25)',
    color: '#e5e7eb',
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    fontSize: '0.8rem',
  },
  myProfilesSummary: {
    background: 'rgba(15, 23, 42, 0.6)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '8px',
    padding: '0.85rem 1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.45rem',
  },
  summaryTitle: {
    fontSize: '0.75rem',
    fontWeight: '700',
    color: '#6366f1',
    letterSpacing: '0.05em',
  },
  summaryRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '0.85rem',
    color: '#f3f4f6',
  },
  connectedBadge: {
    color: '#34d399',
    fontWeight: '600',
    fontSize: '0.8rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.3rem',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
  },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.35rem',
  },
  fieldLabelRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.45rem',
  },
  fieldTitle: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#e5e7eb',
  },
  inputRow: {
    display: 'flex',
    gap: '0.5rem',
  },
  errorText: {
    color: '#f87171',
    fontSize: '0.78rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.35rem',
    marginTop: '0.2rem',
  },
  actions: {
    marginTop: '0.5rem',
  },
};

export default OnboardingPage;
