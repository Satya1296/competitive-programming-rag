import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { platformApi } from '../services/api';
import {
  UserCheck,
  Flame,
  Code,
  Database,
  Link as LinkIcon,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  ShieldCheck,
  Key,
} from 'lucide-react';

const MyProfilesPage = () => {
  const { user } = useAuth();

  const [activePlatformTab, setActivePlatformTab] = useState('codeforces');

  // Input states
  const [cfHandle, setCfHandle] = useState('');
  const [cfApiKey, setCfApiKey] = useState('');
  const [cfApiSecret, setCfApiSecret] = useState('');

  const [lcHandle, setLcHandle] = useState('');
  const [ccHandle, setCcHandle] = useState('');

  // Status & UI state
  const [platformStatuses, setPlatformStatuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState('');
  const [error, setError] = useState('');

  const fetchStatuses = async () => {
    setLoading(true);
    setError('');
    try {
      const statuses = await platformApi.getAllStatuses();
      setPlatformStatuses(statuses);

      const cf = statuses.find((s) => s.platform === 'codeforces');
      if (cf) setCfHandle(cf.handle || '');

      const lc = statuses.find((s) => s.platform === 'leetcode');
      if (lc) setLcHandle(lc.handle || '');

      const cc = statuses.find((s) => s.platform === 'codechef');
      if (cc) setCcHandle(cc.handle || '');
    } catch (err) {
      console.error('Failed to load platform statuses:', err);
      setPlatformStatuses([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatuses();
  }, []);

  const handleConnect = async (e, platform) => {
    e.preventDefault();
    setConnecting(true);
    setSyncMessage('');
    setError('');

    try {
      if (platform === 'codeforces') {
        if (!cfHandle.trim()) return;
        const res = await platformApi.connectCodeforces(
          cfHandle.trim(),
          cfApiKey.trim() || null,
          cfApiSecret.trim() || null
        );
        setSyncMessage(`Codeforces profile '${res.handle}' connected successfully!`);
      } else if (platform === 'leetcode') {
        if (!lcHandle.trim()) return;
        const res = await platformApi.connectLeetCode(lcHandle.trim());
        setSyncMessage(`LeetCode profile '${res.handle}' connected successfully!`);
      } else if (platform === 'codechef') {
        if (!ccHandle.trim()) return;
        const res = await platformApi.connectCodeChef(ccHandle.trim());
        setSyncMessage(`CodeChef profile '${res.handle}' connected successfully!`);
      }
      await fetchStatuses();
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
      setError(msg);
    } finally {
      setConnecting(false);
    }
  };

  const handleSync = async (platform) => {
    setSyncing(true);
    setSyncMessage('');
    setError('');

    try {
      let syncRes;
      if (platform === 'codeforces') {
        syncRes = await platformApi.syncCodeforces();
      } else if (platform === 'leetcode') {
        syncRes = await platformApi.syncLeetCode();
      } else if (platform === 'codechef') {
        syncRes = await platformApi.syncCodeChef();
      }
      setSyncMessage(syncRes.message || `${platform} submissions synced successfully.`);
      await fetchStatuses();
    } catch (err) {
      let msg = err.response?.data?.detail;
      if (Array.isArray(msg)) {
        msg = msg.map((m) => m.msg || m.message || JSON.stringify(m)).join(', ');
      } else if (typeof msg === 'object' && msg !== null) {
        msg = msg.message || JSON.stringify(msg);
      }
      if (!msg) {
        msg = err.message || `Failed to sync ${platform} submissions.`;
      }
      setError(msg);
    } finally {
      setSyncing(false);
    }
  };

  const getStatus = (plat) => platformStatuses.find((s) => s.platform === plat);
  const cfStatus = getStatus('codeforces');
  const lcStatus = getStatus('leetcode');
  const ccStatus = getStatus('codechef');

  return (
    <div style={styles.container}>
      {/* Header Banner */}
      <div className="glass-panel" style={styles.headerBanner}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <UserCheck size={24} color="#818cf8" />
            <h1 style={styles.title}>My Profiles</h1>
          </div>
          <p style={styles.subtitle}>
            Manage your personal competitive programming accounts ({user?.username}).
          </p>
        </div>

        <div style={styles.badge}>
          <ShieldCheck size={16} color="#6366f1" />
          <span>User-Isolated RAG Context</span>
        </div>
      </div>

      {/* Overview Status Cards */}
      <div style={styles.overviewGrid}>
        <div className="glass-panel" style={styles.statusCard}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Flame size={20} color="#f59e0b" />
            <span style={styles.cardTitle}>Codeforces</span>
          </div>
          {cfStatus ? (
            <div>
              <div style={styles.cardValue}>{cfStatus.handle}</div>
              <div style={styles.cardMeta}>
                {cfStatus.total_submissions_synced} synced •{' '}
                {cfStatus.has_api_credentials ? 'Full Auth' : 'Metadata'}
              </div>
            </div>
          ) : (
            <div style={styles.notConnected}>Not Connected</div>
          )}
        </div>

        <div className="glass-panel" style={styles.statusCard}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Code size={20} color="#fbbf24" />
            <span style={styles.cardTitle}>LeetCode</span>
          </div>
          {lcStatus ? (
            <div>
              <div style={styles.cardValue}>{lcStatus.handle}</div>
              <div style={styles.cardMeta}>{lcStatus.total_submissions_synced} synced</div>
            </div>
          ) : (
            <div style={styles.notConnected}>Not Connected</div>
          )}
        </div>

        <div className="glass-panel" style={styles.statusCard}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Database size={20} color="#34d399" />
            <span style={styles.cardTitle}>CodeChef</span>
          </div>
          {ccStatus ? (
            <div>
              <div style={styles.cardValue}>{ccStatus.handle}</div>
              <div style={styles.cardMeta}>{ccStatus.total_submissions_synced} synced</div>
            </div>
          ) : (
            <div style={styles.notConnected}>Not Connected</div>
          )}
        </div>
      </div>

      {/* Main Connection & Management Panel */}
      <div className="glass-panel" style={styles.mainCard}>
        {/* Navigation Tabs */}
        <div style={styles.tabHeader}>
          <button
            onClick={() => setActivePlatformTab('codeforces')}
            style={{
              ...styles.tabBtn,
              ...(activePlatformTab === 'codeforces' ? styles.tabBtnActive : {}),
            }}
          >
            <Flame size={16} color="#f59e0b" /> Codeforces
            {cfStatus && <span style={styles.activeDot} />}
          </button>

          <button
            onClick={() => setActivePlatformTab('leetcode')}
            style={{
              ...styles.tabBtn,
              ...(activePlatformTab === 'leetcode' ? styles.tabBtnActive : {}),
            }}
          >
            <Code size={16} color="#fbbf24" /> LeetCode
            {lcStatus && <span style={styles.activeDot} />}
          </button>

          <button
            onClick={() => setActivePlatformTab('codechef')}
            style={{
              ...styles.tabBtn,
              ...(activePlatformTab === 'codechef' ? styles.tabBtnActive : {}),
            }}
          >
            <Database size={16} color="#34d399" /> CodeChef
            {ccStatus && <span style={styles.activeDot} />}
          </button>
        </div>

        {/* Codeforces Form & Status */}
        {activePlatformTab === 'codeforces' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={styles.formHeader}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: '700', color: '#f3f4f6' }}>
                  Codeforces Account Setup
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: '0.2rem' }}>
                  {cfStatus
                    ? `Currently connected to handle '${cfStatus.handle}'. Updating your handle will safely purge old Codeforces vectors and records.`
                    : 'Enter your personal Codeforces handle. API credentials enable source code retrieval.'}
                </p>
              </div>

              {cfStatus && (
                <button
                  onClick={() => handleSync('codeforces')}
                  disabled={syncing}
                  className="btn-primary"
                >
                  <RefreshCw size={16} className={syncing ? 'spin' : ''} />
                  <span>{syncing ? 'Syncing...' : 'Sync Submissions'}</span>
                </button>
              )}
            </div>

            <form onSubmit={(e) => handleConnect(e, 'codeforces')} style={styles.form}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1, minWidth: '200px' }}>
                <label style={styles.label}>Codeforces Handle</label>
                <input
                  type="text"
                  placeholder="e.g. tourist, Jyoascoder"
                  value={cfHandle}
                  onChange={(e) => setCfHandle(e.target.value)}
                  className="input-field"
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1, minWidth: '180px' }}>
                <label style={styles.label}>API Key (Optional)</label>
                <input
                  type="text"
                  placeholder="Codeforces API Key"
                  value={cfApiKey}
                  onChange={(e) => setCfApiKey(e.target.value)}
                  className="input-field"
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1, minWidth: '180px' }}>
                <label style={styles.label}>API Secret (Optional)</label>
                <input
                  type="password"
                  placeholder="Codeforces API Secret"
                  value={cfApiSecret}
                  onChange={(e) => setCfApiSecret(e.target.value)}
                  className="input-field"
                />
              </div>

              <button type="submit" className="btn-secondary" disabled={connecting} style={{ alignSelf: 'flex-end' }}>
                <LinkIcon size={16} />
                <span>{connecting ? 'Validating...' : cfStatus ? 'Update Profile' : 'Connect Profile'}</span>
              </button>
            </form>
          </div>
        )}

        {/* LeetCode Form & Status */}
        {activePlatformTab === 'leetcode' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={styles.formHeader}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: '700', color: '#f3f4f6' }}>
                  LeetCode Account Setup
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: '0.2rem' }}>
                  {lcStatus
                    ? `Currently connected to LeetCode username '${lcStatus.handle}'.`
                    : 'Enter your personal LeetCode username to sync recent submissions.'}
                </p>
              </div>

              {lcStatus && (
                <button
                  onClick={() => handleSync('leetcode')}
                  disabled={syncing}
                  className="btn-primary"
                >
                  <RefreshCw size={16} className={syncing ? 'spin' : ''} />
                  <span>{syncing ? 'Syncing...' : 'Sync Submissions'}</span>
                </button>
              )}
            </div>

            <form onSubmit={(e) => handleConnect(e, 'leetcode')} style={styles.form}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxWidth: '400px', width: '100%' }}>
                <label style={styles.label}>LeetCode Username</label>
                <input
                  type="text"
                  placeholder="e.g. Pragnya, NebulaOfCodeRK"
                  value={lcHandle}
                  onChange={(e) => setLcHandle(e.target.value)}
                  className="input-field"
                />
              </div>

              <button type="submit" className="btn-secondary" disabled={connecting} style={{ alignSelf: 'flex-end' }}>
                <LinkIcon size={16} />
                <span>{connecting ? 'Validating...' : lcStatus ? 'Update Username' : 'Connect LeetCode'}</span>
              </button>
            </form>
          </div>
        )}

        {/* CodeChef Form & Status */}
        {activePlatformTab === 'codechef' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div style={styles.formHeader}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: '700', color: '#f3f4f6' }}>
                  CodeChef Account Setup
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: '0.2rem' }}>
                  {ccStatus
                    ? `Currently connected to CodeChef username '${ccStatus.handle}'.`
                    : 'Enter your personal CodeChef username to sync recent submissions.'}
                </p>
              </div>

              {ccStatus && (
                <button
                  onClick={() => handleSync('codechef')}
                  disabled={syncing}
                  className="btn-primary"
                >
                  <RefreshCw size={16} className={syncing ? 'spin' : ''} />
                  <span>{syncing ? 'Syncing...' : 'Sync Submissions'}</span>
                </button>
              )}
            </div>

            <form onSubmit={(e) => handleConnect(e, 'codechef')} style={styles.form}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxWidth: '400px', width: '100%' }}>
                <label style={styles.label}>CodeChef Username</label>
                <input
                  type="text"
                  placeholder="e.g. admin, chef_user"
                  value={ccHandle}
                  onChange={(e) => setCcHandle(e.target.value)}
                  className="input-field"
                />
              </div>

              <button type="submit" className="btn-secondary" disabled={connecting} style={{ alignSelf: 'flex-end' }}>
                <LinkIcon size={16} />
                <span>{connecting ? 'Validating...' : ccStatus ? 'Update Username' : 'Connect CodeChef'}</span>
              </button>
            </form>
          </div>
        )}

        {syncMessage && (
          <div style={styles.successAlert}>
            <CheckCircle size={16} />
            <span>{syncMessage}</span>
          </div>
        )}

        {error && (
          <div style={styles.errorAlert}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}
      </div>
    </div>
  );
};

const styles = {
  container: {
    padding: '2rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1.5rem',
  },
  headerBanner: {
    padding: '1.5rem 2rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    flexWrap: 'wrap',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: '800',
    color: '#f9fafb',
  },
  subtitle: {
    color: '#9ca3af',
    fontSize: '0.85rem',
    marginTop: '0.2rem',
  },
  badge: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    background: 'rgba(99, 102, 241, 0.1)',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    color: '#818cf8',
    padding: '0.5rem 0.85rem',
    borderRadius: '8px',
    fontSize: '0.8rem',
    fontWeight: '600',
  },
  overviewGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: '1.25rem',
  },
  statusCard: {
    padding: '1.25rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  cardTitle: {
    fontSize: '0.95rem',
    fontWeight: '700',
    color: '#f3f4f6',
  },
  cardValue: {
    fontSize: '1.15rem',
    fontWeight: '700',
    color: '#a5b4fc',
    fontFamily: 'var(--font-code)',
  },
  cardMeta: {
    fontSize: '0.75rem',
    color: '#9ca3af',
    marginTop: '0.15rem',
  },
  notConnected: {
    fontSize: '0.85rem',
    color: '#6b7280',
    fontStyle: 'italic',
  },
  mainCard: {
    padding: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
  },
  tabHeader: {
    display: 'flex',
    gap: '0.75rem',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
    paddingBottom: '0.75rem',
  },
  tabBtn: {
    padding: '0.45rem 0.85rem',
    borderRadius: '8px',
    border: '1px solid transparent',
    background: 'rgba(255, 255, 255, 0.03)',
    color: '#9ca3af',
    fontSize: '0.85rem',
    fontWeight: '600',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '0.45rem',
    position: 'relative',
    transition: 'all 0.2s',
  },
  tabBtnActive: {
    background: 'rgba(99, 102, 241, 0.15)',
    color: '#a5b4fc',
    border: '1px solid rgba(99, 102, 241, 0.3)',
  },
  activeDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: '#10b981',
    marginLeft: '0.2rem',
  },
  formHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    flexWrap: 'wrap',
  },
  form: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '0.85rem',
    flexWrap: 'wrap',
  },
  label: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#9ca3af',
  },
  successAlert: {
    background: 'rgba(16, 185, 129, 0.15)',
    border: '1px solid rgba(16, 185, 129, 0.3)',
    color: '#34d399',
    padding: '0.65rem 1rem',
    borderRadius: '8px',
    fontSize: '0.85rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  errorAlert: {
    background: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    color: '#f87171',
    padding: '0.65rem 1rem',
    borderRadius: '8px',
    fontSize: '0.85rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
};

export default MyProfilesPage;
