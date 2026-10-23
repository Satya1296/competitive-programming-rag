import React, { useState, useMemo } from 'react';
import { Search, Filter, Code, ExternalLink, ArrowUpDown } from 'lucide-react';

const SubmissionsTable = ({ submissions = [], onSelectSubmission, loading, error }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [verdictFilter, setVerdictFilter] = useState('ALL');
  const [languageFilter, setLanguageFilter] = useState('ALL');

  const [platformFilter, setPlatformFilter] = useState('ALL');

  // Filtered submissions
  const filteredData = useMemo(() => {
    return submissions.filter((sub) => {
      const matchesSearch =
        sub.problem_title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        sub.problem_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (sub.tags && sub.tags.some((t) => t.toLowerCase().includes(searchTerm.toLowerCase())));

      const matchesPlatform =
        platformFilter === 'ALL' || sub.platform.toLowerCase() === platformFilter.toLowerCase();

      const matchesVerdict =
        verdictFilter === 'ALL' || sub.verdict === verdictFilter;

      const matchesLanguage =
        languageFilter === 'ALL' || sub.language.toLowerCase() === languageFilter.toLowerCase();

      return matchesSearch && matchesPlatform && matchesVerdict && matchesLanguage;
    });
  }, [submissions, searchTerm, platformFilter, verdictFilter, languageFilter]);

  if (loading) {
    return (
      <div style={styles.stateContainer}>
        <div style={styles.spinner} />
        <p style={{ color: '#9ca3af', marginTop: '1rem' }}>Loading user submissions...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.stateContainer}>
        <p style={{ color: '#f87171' }}>Error loading submissions: {error}</p>
      </div>
    );
  }

  return (
    <div className="glass-panel" style={styles.container}>
      {/* Search & Filter Toolbar */}
      <div style={styles.toolbar}>
        <div style={styles.searchBox}>
          <Search size={16} color="#9ca3af" />
          <input
            type="text"
            placeholder="Search by problem name, ID, or tag..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={styles.searchInput}
          />
        </div>

        <div style={styles.filterGroup}>
          <Filter size={16} color="#9ca3af" />
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            style={styles.selectInput}
          >
            <option value="ALL">All Platforms</option>
            <option value="codeforces">Codeforces</option>
            <option value="leetcode">LeetCode</option>
            <option value="codechef">CodeChef</option>
          </select>


          <select
            value={verdictFilter}
            onChange={(e) => setVerdictFilter(e.target.value)}
            style={styles.selectInput}
          >
            <option value="ALL">All Verdicts</option>
            <option value="ACCEPTED">ACCEPTED</option>
            <option value="WRONG_ANSWER">WRONG ANSWER</option>
            <option value="TIME_LIMIT_EXCEEDED">TIME LIMIT EXCEEDED</option>
          </select>

          <select
            value={languageFilter}
            onChange={(e) => setLanguageFilter(e.target.value)}
            style={styles.selectInput}
          >
            <option value="ALL">All Languages</option>
            <option value="cpp">C++</option>
            <option value="python">Python</option>
            <option value="java">Java</option>
          </select>
        </div>
      </div>

      {/* Table */}
      {filteredData.length === 0 ? (
        <div style={styles.emptyState}>
          <Code size={36} color="#4b5563" />
          <p style={{ color: '#9ca3af', fontWeight: '500' }}>No submissions found matching your filters.</p>
          {submissions.length === 0 && (
            <p style={{ fontSize: '0.8rem', color: '#6b7280' }}>
              Connect your Codeforces handle above and click <strong>Sync Submissions</strong> to import your history.
            </p>
          )}
        </div>
      ) : (
        <div style={styles.tableWrapper}>
          <table style={styles.table}>
            <thead>
              <tr style={styles.thRow}>
                <th style={styles.th}>Platform</th>
                <th style={styles.th}>Problem Name & ID</th>
                <th style={styles.th}>Verdict</th>
                <th style={styles.th}>Language</th>
                <th style={styles.th}>Difficulty</th>
                <th style={styles.th}>Submitted Date</th>
                <th style={styles.th}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredData.map((sub) => (
                <tr
                  key={sub.id}
                  style={styles.tr}
                  onClick={() => onSelectSubmission(sub)}
                >
                  <td style={styles.td}>
                    <span className="badge badge-platform">{sub.platform}</span>
                  </td>
                  <td style={styles.td}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: '600', color: '#f3f4f6' }}>
                        {sub.problem_title}
                      </span>
                      {(() => {
                        const hasCode =
                          sub.has_source_code !== undefined
                            ? sub.has_source_code
                            : sub.code_source !== 'api_metadata' &&
                              sub.code &&
                              !sub.code.startsWith('// Source code not provided');
                        return (
                          <span
                            style={{
                              padding: '0.1rem 0.4rem',
                              borderRadius: '4px',
                              fontSize: '0.68rem',
                              fontWeight: '600',
                              background: hasCode ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                              color: hasCode ? '#34d399' : '#fbbf24',
                              border: hasCode
                                ? '1px solid rgba(16, 185, 129, 0.3)'
                                : '1px solid rgba(245, 158, 11, 0.3)',
                            }}
                          >
                            {hasCode ? 'Code Attached' : 'Metadata Only'}
                          </span>
                        );
                      })()}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                      Code: {sub.problem_id}
                    </div>
                  </td>
                  <td style={styles.td}>
                    <span
                      className={`badge ${
                        sub.verdict === 'ACCEPTED' ? 'badge-accepted' : 'badge-wrong'
                      }`}
                    >
                      {sub.verdict}
                    </span>
                  </td>
                  <td style={styles.td}>
                    <span style={styles.langTag}>{sub.language}</span>
                  </td>
                  <td style={styles.td}>
                    {sub.difficulty ? (
                      <span style={styles.diffBadge}>{sub.difficulty}</span>
                    ) : (
                      <span style={{ color: '#6b7280' }}>-</span>
                    )}
                  </td>
                  <td style={styles.td}>
                    <span style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                      {new Date(sub.submitted_at).toLocaleDateString()}
                    </span>
                  </td>
                  <td style={styles.td}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectSubmission(sub);
                      }}
                      className="btn-secondary"
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
                    >
                      <Code size={14} />
                      View Code
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const styles = {
  container: {
    padding: '1.25rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    flexWrap: 'wrap',
  },
  searchBox: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    background: 'rgba(15, 23, 42, 0.8)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '8px',
    padding: '0.5rem 0.75rem',
    flex: 1,
    minWidth: '240px',
  },
  searchInput: {
    background: 'transparent',
    border: 'none',
    color: '#f9fafb',
    width: '100%',
    outline: 'none',
    fontSize: '0.9rem',
    fontFamily: 'inherit',
  },
  filterGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  selectInput: {
    background: '#1e293b',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    color: '#f3f4f6',
    borderRadius: '6px',
    padding: '0.5rem 0.75rem',
    fontSize: '0.85rem',
    outline: 'none',
    cursor: 'pointer',
  },
  stateContainer: {
    padding: '3rem',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
  },
  spinner: {
    width: '32px',
    height: '32px',
    border: '3px solid rgba(99, 102, 241, 0.2)',
    borderTopColor: '#6366f1',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  emptyState: {
    padding: '3rem',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.5rem',
    textAlign: 'center',
  },
  tableWrapper: {
    overflowX: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    textAlign: 'left',
  },
  thRow: {
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  },
  th: {
    padding: '0.75rem 1rem',
    fontSize: '0.75rem',
    fontWeight: '600',
    color: '#9ca3af',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  tr: {
    borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
  td: {
    padding: '0.9rem 1rem',
    fontSize: '0.875rem',
    verticalAlign: 'middle',
  },
  langTag: {
    fontFamily: 'var(--font-code)',
    fontSize: '0.8rem',
    background: 'rgba(255, 255, 255, 0.05)',
    padding: '0.2rem 0.5rem',
    borderRadius: '4px',
    color: '#cbd5e1',
  },
  diffBadge: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#fbbf24',
    background: 'rgba(245, 158, 11, 0.1)',
    padding: '0.15rem 0.5rem',
    borderRadius: '4px',
  },
};

export default SubmissionsTable;
