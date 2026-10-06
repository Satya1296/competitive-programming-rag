import React, { useState } from 'react';
import { publicProfilesApi } from '../services/api';
import { Users, Search, AlertCircle, CheckCircle, Flame, Code, Database, ExternalLink, ShieldCheck } from 'lucide-react';

const PublicProfilesPage = () => {
  const [platform, setPlatform] = useState('codeforces');
  const [username, setUsername] = useState('');
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!username.trim()) return;

    setSearching(true);
    setError('');
    setResult(null);

    try {
      const data = await publicProfilesApi.search(platform, username.trim());
      setResult(data);
    } catch (err) {
      let msg = err.response?.data?.detail;
      if (Array.isArray(msg)) {
        msg = msg.map((m) => m.msg || m.message || JSON.stringify(m)).join(', ');
      } else if (typeof msg === 'object' && msg !== null) {
        msg = msg.message || JSON.stringify(msg);
      }
      if (!msg) {
        msg = err.message || `Failed to fetch public ${platform} profile.`;
      }
      setError(msg);
    } finally {
      setSearching(false);
    }
  };

  const getPlatformIcon = (plat) => {
    if (plat === 'codeforces') return <Flame size={18} color="#f59e0b" />;
    if (plat === 'leetcode') return <Code size={18} color="#fbbf24" />;
    return <Database size={18} color="#34d399" />;
  };

  return (
    <div style={styles.container}>
      {/* Header Banner */}
      <div className="glass-panel" style={styles.headerBanner}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <Users size={24} color="#818cf8" />
            <h1 style={styles.title}>Friends / Public Profiles Search</h1>
          </div>
          <p style={styles.subtitle}>
            Search public handles across Codeforces, LeetCode, and CodeChef to view external activity.
          </p>
        </div>

        <div style={styles.isolationBadge}>
          <ShieldCheck size={16} color="#34d399" />
          <span>Transient Search Only — Does NOT pollute your personal dataset</span>
        </div>
      </div>

      {/* Search Form Card */}
      <div className="glass-panel" style={styles.searchCard}>
        <form onSubmit={handleSearch} style={styles.form}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
            <label style={styles.label}>Platform</label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              className="input-field"
              style={{ minWidth: '160px' }}
            >
              <option value="codeforces">Codeforces</option>
              <option value="leetcode">LeetCode</option>
              <option value="codechef">CodeChef</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', flex: 1, minWidth: '220px' }}>
            <label style={styles.label}>Public Username / Handle</label>
            <input
              type="text"
              placeholder="e.g. tourist, neal_wu, hiepit, admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input-field"
            />
          </div>

          <button type="submit" className="btn-primary" disabled={searching} style={{ alignSelf: 'flex-end' }}>
            <Search size={16} />
            <span>{searching ? 'Searching...' : 'Search Profile'}</span>
          </button>
        </form>

        {error && (
          <div style={styles.errorAlert}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Result Display */}
      {result && (
        <div className="glass-panel" style={styles.resultCard}>
          <div style={styles.resultHeader}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              {getPlatformIcon(result.platform)}
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: '700', color: '#f3f4f6' }}>
                  {result.title_or_name || result.username}
                </h3>
                <span style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                  Public {result.platform.toUpperCase()} handle: <strong>{result.username}</strong>
                </span>
              </div>
            </div>

            {result.rank_or_rating && (
              <span style={styles.rankBadge}>{result.rank_or_rating}</span>
            )}
          </div>

          <div style={styles.metricsGrid}>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>Profile Status</span>
              <span style={{ fontSize: '0.95rem', fontWeight: '600', color: '#34d399', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <CheckCircle size={14} /> Valid Public Handle
              </span>
            </div>

            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>Recent Submissions Sampled</span>
              <span style={{ fontSize: '1.1rem', fontWeight: '700', color: '#818cf8' }}>
                {result.total_solved}
              </span>
            </div>
          </div>

          {/* Recent Activity Table */}
          {result.recent_activity && result.recent_activity.length > 0 ? (
            <div style={{ marginTop: '1rem' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: '600', color: '#e5e7eb', marginBottom: '0.65rem' }}>
                Recent Public Activity Sample
              </h4>
              <div style={{ overflowX: 'auto' }}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Problem</th>
                      <th style={styles.th}>Verdict</th>
                      <th style={styles.th}>Language</th>
                      <th style={styles.th}>Timestamp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.recent_activity.map((act, idx) => (
                      <tr key={idx} style={styles.tr}>
                        <td style={styles.td}>
                          <a
                            href={act.problem_url || '#'}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={styles.link}
                          >
                            <span>{act.problem_title}</span>
                            <ExternalLink size={12} />
                          </a>
                        </td>
                        <td style={styles.td}>
                          <span style={act.verdict === 'ACCEPTED' ? styles.verdictAc : styles.verdictOther}>
                            {act.verdict}
                          </span>
                        </td>
                        <td style={styles.td}>{act.language || 'unknown'}</td>
                        <td style={styles.td}>{act.submitted_at || 'Recent'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p style={{ fontSize: '0.85rem', color: '#9ca3af', marginTop: '0.5rem' }}>
              No recent public activity rows returned for this handle.
            </p>
          )}
        </div>
      )}
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
  isolationBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    background: 'rgba(52, 211, 153, 0.1)',
    border: '1px solid rgba(52, 211, 153, 0.3)',
    color: '#34d399',
    padding: '0.5rem 0.85rem',
    borderRadius: '8px',
    fontSize: '0.8rem',
    fontWeight: '600',
  },
  searchCard: {
    padding: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  form: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '1rem',
    flexWrap: 'wrap',
  },
  label: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#9ca3af',
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
  resultCard: {
    padding: '1.5rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  resultHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
    paddingBottom: '1rem',
  },
  rankBadge: {
    background: 'rgba(99, 102, 241, 0.15)',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    color: '#a5b4fc',
    padding: '0.35rem 0.75rem',
    borderRadius: '6px',
    fontSize: '0.8rem',
    fontWeight: '600',
  },
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '1rem',
  },
  metricItem: {
    background: 'rgba(15, 23, 42, 0.5)',
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    border: '1px solid rgba(255, 255, 255, 0.05)',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  metricLabel: {
    fontSize: '0.75rem',
    color: '#9ca3af',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '0.85rem',
  },
  th: {
    textAlign: 'left',
    padding: '0.6rem 0.85rem',
    color: '#9ca3af',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
    fontWeight: '600',
  },
  tr: {
    borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
  },
  td: {
    padding: '0.6rem 0.85rem',
    color: '#e5e7eb',
  },
  link: {
    color: '#818cf8',
    textDecoration: 'none',
    display: 'flex',
    alignItems: 'center',
    gap: '0.35rem',
  },
  verdictAc: {
    color: '#34d399',
    fontWeight: '600',
  },
  verdictOther: {
    color: '#f87171',
    fontWeight: '500',
  },
};

export default PublicProfilesPage;
