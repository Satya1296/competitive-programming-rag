import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { platformApi, submissionApi } from '../services/api';
import StatCard from '../components/StatCard';
import SubmissionsTable from '../components/SubmissionsTable';
import CodeViewerModal from '../components/CodeViewerModal';
import {
  Code,
  CheckCircle,
  RefreshCw,
  Link as LinkIcon,
  Tag,
  AlertCircle,
  Database,
  Flame,
} from 'lucide-react';

const DashboardPage = () => {
  const { user } = useAuth();

  // Platform State
  const [activePlatformTab, setActivePlatformTab] = useState('codeforces');
  const [cfHandleInput, setCfHandleInput] = useState('');
  const [cfApiKeyInput, setCfApiKeyInput] = useState('');
  const [cfApiSecretInput, setCfApiSecretInput] = useState('');

  const [lcHandleInput, setLcHandleInput] = useState('');
  const [ccHandleInput, setCcHandleInput] = useState('');

  const [platformStatuses, setPlatformStatuses] = useState([]);
  const [statsData, setStatsData] = useState(null);

  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState('');

  // Submissions data
  const [submissions, setSubmissions] = useState([]);
  const [loadingSubs, setLoadingSubs] = useState(true);
  const [error, setError] = useState('');
  const [selectedSub, setSelectedSub] = useState(null);

  // Fetch statuses, stats & submissions
  const loadDashboardData = async () => {
    setLoadingSubs(true);
    setError('');
    try {
      // 1. Fetch all platform statuses
      try {
        const statuses = await platformApi.getAllStatuses();
        setPlatformStatuses(statuses);

        const cf = statuses.find((s) => s.platform === 'codeforces');
        if (cf) setCfHandleInput(cf.handle);

        const lc = statuses.find((s) => s.platform === 'leetcode');
        if (lc) setLcHandleInput(lc.handle);

        const cc = statuses.find((s) => s.platform === 'codechef');
        if (cc) setCcHandleInput(cc.handle);
      } catch (err) {
        setPlatformStatuses([]);
      }

      // 2. Fetch platform stats
      try {
        const st = await platformApi.getStats();
        setStatsData(st);
      } catch (err) {
        setStatsData(null);
      }

      // 3. Fetch User Submissions
      const subsData = await submissionApi.getSubmissions();
      setSubmissions(subsData);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
      setError('Failed to fetch user submission records.');
    } finally {
      setLoadingSubs(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  // Handle Connect Profile per platform
  const handleConnectPlatform = async (e, platform) => {
    e.preventDefault();
    setConnecting(true);
    setSyncMessage('');
    setError('');

    try {
      if (platform === 'codeforces') {
        if (!cfHandleInput.trim()) return;
        const res = await platformApi.connectCodeforces(
          cfHandleInput.trim(),
          cfApiKeyInput.trim() || null,
          cfApiSecretInput.trim() || null
        );
        setSyncMessage(`Codeforces handle '${res.handle}' connected successfully!`);
      } else if (platform === 'leetcode') {
        if (!lcHandleInput.trim()) return;
        const res = await platformApi.connectLeetCode(lcHandleInput.trim());
        setSyncMessage(`LeetCode user '${res.handle}' connected successfully!`);
      } else if (platform === 'codechef') {
        if (!ccHandleInput.trim()) return;
        const res = await platformApi.connectCodeChef(ccHandleInput.trim());
        setSyncMessage(`CodeChef user '${res.handle}' connected successfully!`);
      }
      await loadDashboardData();
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

  // Handle Sync Submissions per platform
  const handleSyncPlatform = async (platform) => {
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
      setSyncMessage(syncRes.message);
      await loadDashboardData();
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

  const getStatusForPlatform = (plat) =>
    platformStatuses.find((s) => s.platform === plat);

  const cfStatus = getStatusForPlatform('codeforces');
  const lcStatus = getStatusForPlatform('leetcode');
  const ccStatus = getStatusForPlatform('codechef');

  return (
    <div style={styles.container}>
      {/* Welcome Banner */}
      <div className="glass-panel" style={styles.welcomeBanner}>
        <div>
          <h1 style={styles.welcomeTitle}>
            Welcome back, <span style={styles.highlightName}>{user?.username}</span> 👋
          </h1>
          <p style={styles.welcomeSubtitle}>
            Multi-platform competitive programming knowledge system (Codeforces, LeetCode, CodeChef).
          </p>
        </div>

        <div style={styles.userBadge}>
          <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Authenticated User ID</span>
          <span style={{ fontSize: '0.85rem', fontWeight: '600', color: '#a5b4fc', fontFamily: 'var(--font-code)' }}>
            {user?.id}
          </span>
        </div>
      </div>

      {/* Multi-Platform Connection Card */}
      <div className="glass-panel" style={styles.cfCard}>
        {/* Tab Header */}
        <div style={styles.platformTabHeader}>
          <button
            onClick={() => setActivePlatformTab('codeforces')}
            style={{
              ...styles.platformTabBtn,
              ...(activePlatformTab === 'codeforces' ? styles.platformTabBtnActive : {}),
            }}
          >
            <Flame size={16} color="#f59e0b" /> Codeforces
            {cfStatus && <span style={styles.activeDot} />}
          </button>

          <button
            onClick={() => setActivePlatformTab('leetcode')}
            style={{
              ...styles.platformTabBtn,
              ...(activePlatformTab === 'leetcode' ? styles.platformTabBtnActive : {}),
            }}
          >
            <Code size={16} color="#fbbf24" /> LeetCode
            {lcStatus && <span style={styles.activeDot} />}
          </button>

          <button
            onClick={() => setActivePlatformTab('codechef')}
            style={{
              ...styles.platformTabBtn,
              ...(activePlatformTab === 'codechef' ? styles.platformTabBtnActive : {}),
            }}
          >
            <Database size={16} color="#34d399" /> CodeChef
            {ccStatus && <span style={styles.activeDot} />}
          </button>
        </div>

        {/* Codeforces Form */}
        {activePlatformTab === 'codeforces' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={styles.cfHeader}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: '700', color: '#f3f4f6' }}>
                  Codeforces Connection
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                  {cfStatus
                    ? `Connected: ${cfStatus.handle} (${cfStatus.total_submissions_synced} synced, ${
                        cfStatus.has_api_credentials ? 'Authenticated Source Retrieval Active' : 'Metadata Only'
                      })`
                    : 'Enter your Codeforces handle (and optional API Key/Secret for automated source retrieval)'}
                </p>
              </div>

              {cfStatus && (
                <button
                  onClick={() => handleSyncPlatform('codeforces')}
                  disabled={syncing}
                  className="btn-primary"
                >
                  <RefreshCw size={16} className={syncing ? 'spin' : ''} />
                  <span>{syncing ? 'Syncing...' : 'Sync Codeforces'}</span>
                </button>
              )}
            </div>

            <form onSubmit={(e) => handleConnectPlatform(e, 'codeforces')} style={styles.cfForm}>
              <input
                type="text"
                placeholder="Codeforces Handle (e.g. tourist)"
                value={cfHandleInput}
                onChange={(e) => setCfHandleInput(e.target.value)}
                className="input-field"
                style={{ flex: 1, minWidth: '220px' }}
              />

              <input
                type="text"
                placeholder="Optional API Key"
                value={cfApiKeyInput}
                onChange={(e) => setCfApiKeyInput(e.target.value)}
                className="input-field"
                style={{ flex: 1, minWidth: '180px' }}
              />

              <input
                type="password"
                placeholder="Optional API Secret"
                value={cfApiSecretInput}
                onChange={(e) => setCfApiSecretInput(e.target.value)}
                className="input-field"
                style={{ flex: 1, minWidth: '180px' }}
              />

              <button type="submit" className="btn-secondary" disabled={connecting}>
                <LinkIcon size={16} />
                <span>{connecting ? 'Validating...' : cfStatus ? 'Update Profile' : 'Connect Profile'}</span>
              </button>
            </form>
          </div>
        )}

        {/* LeetCode Form */}
        {activePlatformTab === 'leetcode' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={styles.cfHeader}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: '700', color: '#f3f4f6' }}>
                  LeetCode Connection
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                  {lcStatus
                    ? `Connected Username: ${lcStatus.handle} (${lcStatus.total_submissions_synced} synced)`
                    : 'Enter your LeetCode username to sync recent submissions metadata'}
                </p>
              </div>

              {lcStatus && (
                <button
                  onClick={() => handleSyncPlatform('leetcode')}
                  disabled={syncing}
                  className="btn-primary"
                >
                  <RefreshCw size={16} className={syncing ? 'spin' : ''} />
                  <span>{syncing ? 'Syncing...' : 'Sync LeetCode'}</span>
                </button>
              )}
            </div>

            <form onSubmit={(e) => handleConnectPlatform(e, 'leetcode')} style={styles.cfForm}>
              <input
                type="text"
                placeholder="LeetCode Username"
                value={lcHandleInput}
                onChange={(e) => setLcHandleInput(e.target.value)}
                className="input-field"
                style={{ maxWidth: '360px' }}
              />

              <button type="submit" className="btn-secondary" disabled={connecting}>
                <LinkIcon size={16} />
                <span>{connecting ? 'Validating...' : lcStatus ? 'Update Username' : 'Connect LeetCode'}</span>
              </button>
            </form>
          </div>
        )}

        {/* CodeChef Form */}
        {activePlatformTab === 'codechef' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={styles.cfHeader}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: '700', color: '#f3f4f6' }}>
                  CodeChef Connection
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                  {ccStatus
                    ? `Connected Username: ${ccStatus.handle} (${ccStatus.total_submissions_synced} synced)`
                    : 'Enter your CodeChef username to sync submissions metadata'}
                </p>
              </div>

              {ccStatus && (
                <button
                  onClick={() => handleSyncPlatform('codechef')}
                  disabled={syncing}
                  className="btn-primary"
                >
                  <RefreshCw size={16} className={syncing ? 'spin' : ''} />
                  <span>{syncing ? 'Syncing...' : 'Sync CodeChef'}</span>
                </button>
              )}
            </div>

            <form onSubmit={(e) => handleConnectPlatform(e, 'codechef')} style={styles.cfForm}>
              <input
                type="text"
                placeholder="CodeChef Username"
                value={ccHandleInput}
                onChange={(e) => setCcHandleInput(e.target.value)}
                className="input-field"
                style={{ maxWidth: '360px' }}
              />

              <button type="submit" className="btn-secondary" disabled={connecting}>
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

      {/* Statistics Cards Grid */}
      <div style={styles.statsGrid}>
        <StatCard
          title="Codeforces"
          value={statsData ? statsData.codeforces_count : 0}
          subtitle="Submissions synced"
          icon={Flame}
          color="#f59e0b"
        />

        <StatCard
          title="LeetCode"
          value={statsData ? statsData.leetcode_count : 0}
          subtitle="Submissions synced"
          icon={Code}
          color="#fbbf24"
        />

        <StatCard
          title="CodeChef"
          value={statsData ? statsData.codechef_count : 0}
          subtitle="Submissions synced"
          icon={Database}
          color="#34d399"
        />

        <StatCard
          title="Source Code Ratio"
          value={statsData ? `${statsData.with_source_code_count} / ${statsData.total_submissions}` : '0 / 0'}
          subtitle={`${statsData ? statsData.metadata_only_count : 0} Metadata Only`}
          icon={CheckCircle}
          color="#10b981"
        />
      </div>

      {/* Submissions Section */}
      <div>
        <div style={styles.sectionHeader}>
          <h3 style={{ fontSize: '1.2rem', fontWeight: '700', color: '#f3f4f6' }}>
            Your Submission Records
          </h3>
          <span style={{ fontSize: '0.85rem', color: '#9ca3af' }}>
            Showing {submissions.length} user-scoped records
          </span>
        </div>

        <SubmissionsTable
          submissions={submissions}
          onSelectSubmission={(sub) => setSelectedSub(sub)}
          loading={loadingSubs}
          error={error}
        />
      </div>

      {/* Code Viewer Modal */}
      <CodeViewerModal
        submission={selectedSub}
        onClose={() => setSelectedSub(null)}
      />
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
  welcomeBanner: {
    padding: '1.5rem 2rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    flexWrap: 'wrap',
  },
  welcomeTitle: {
    fontSize: '1.6rem',
    fontWeight: '800',
    color: '#f9fafb',
  },
  highlightName: {
    color: '#818cf8',
  },
  welcomeSubtitle: {
    color: '#9ca3af',
    fontSize: '0.9rem',
    marginTop: '0.2rem',
  },
  userBadge: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    background: 'rgba(15, 23, 42, 0.6)',
    padding: '0.5rem 0.85rem',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.08)',
  },
  cfCard: {
    padding: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1.2rem',
  },
  platformTabHeader: {
    display: 'flex',
    gap: '0.75rem',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
    paddingBottom: '0.75rem',
  },
  platformTabBtn: {
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
  platformTabBtnActive: {
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
  cfHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    flexWrap: 'wrap',
  },
  cfBadgeIcon: {
    width: '42px',
    height: '42px',
    borderRadius: '10px',
    background: 'rgba(245, 158, 11, 0.15)',
    border: '1px solid rgba(245, 158, 11, 0.3)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cfForm: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    flexWrap: 'wrap',
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
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: '1.25rem',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '0.85rem',
  },
};

export default DashboardPage;
