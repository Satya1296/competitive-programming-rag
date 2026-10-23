import React, { useState } from 'react';
import { Search, Sparkles, Database, Code, CheckCircle, AlertCircle, RefreshCw, ExternalLink, Zap } from 'lucide-react';
import { vectorApi, submissionApi } from '../services/api';
import CodeViewerModal from '../components/CodeViewerModal';

const EXAMPLE_QUERIES = [
  'How did I implement binary search?',
  'Show me prefix sums or range query solutions',
  'Dynamic programming on trees or subtrees',
  'Graph traversal using BFS or DFS',
  'Greedy approach with sorting',
];

const SearchPage = () => {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [indexingAll, setIndexingAll] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');
  const [statusMsg, setStatusMsg] = useState('');
  const [selectedSub, setSelectedSub] = useState(null);

  // Handle Search submit
  const handleSearch = async (e, customQuery = null) => {
    if (e) e.preventDefault();
    const searchQuery = customQuery || query;
    if (!searchQuery.trim()) return;

    setSearching(true);
    setError('');
    setStatusMsg('');

    try {
      const data = await vectorApi.searchKnowledge(searchQuery.trim(), 20);
      setResults(data);
      if (data.total_results === 0) {
        setStatusMsg('No matching vectors found for your query. Try indexing your submissions first!');
      }
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to execute semantic search.';
      setError(msg);
    } finally {
      setSearching(false);
    }
  };

  // Handle Bulk Indexing
  const handleIndexAll = async () => {
    setIndexingAll(true);
    setError('');
    setStatusMsg('');

    try {
      const res = await vectorApi.indexAllSubmissions();
      setStatusMsg(res.message);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to index user submissions.';
      setError(msg);
    } finally {
      setIndexingAll(false);
    }
  };

  // Open Code Viewer for a result submission
  const handleOpenCodeViewer = async (item) => {
    try {
      const submissionId = item.submission_id || item.id;
      // Fetch user submissions to check for active SQLite platform submission
      const allSubs = await submissionApi.getSubmissions().catch(() => []);
      let matched = allSubs.find((s) => s.submission_id === submissionId || s.id === submissionId);
      
      // If not directly matched by submission ID, attempt matching by problem ID or Title
      if (!matched && item.problem_id) {
        matched = allSubs.find(
          (s) => s.problem_id && s.problem_id.toString().toLowerCase() === item.problem_id.toString().toLowerCase()
        );
      }
      if (!matched && item.problem_title) {
        matched = allSubs.find(
          (s) => s.problem_title && s.problem_title.toLowerCase() === item.problem_title.toLowerCase()
        );
      }

      if (matched) {
        setSelectedSub(matched);
      } else {
        // Standalone GitHub solution or record without SQLite submission
        let extractedCode = '';
        if (item.document_text) {
          const codeBlockMatch = item.document_text.match(/## Source Code\s*```[a-zA-Z0-9_\-]*\n([\s\S]*?)```/);
          if (codeBlockMatch) {
            extractedCode = codeBlockMatch[1].trim();
          } else {
            extractedCode = item.document_text.trim();
          }
        }

        let ghUrl = null;
        if (item.document_text) {
          const notesMatch = item.document_text.match(/\*\*Notes\*\*:\s*Synced from GitHub repo ([^:\n]+):\s*([^\n]+)/);
          if (notesMatch) {
            const repo = notesMatch[1].trim();
            const path = notesMatch[2].trim();
            ghUrl = `https://github.com/${repo}/blob/main/${path}`;
          }
        }

        const standaloneSub = {
          id: submissionId,
          submission_id: submissionId,
          problem_id: item.problem_id || '',
          problem_title: item.problem_title || 'GitHub Solution',
          platform: item.platform || 'github',
          language: item.language || 'cpp',
          verdict: 'ACCEPTED',
          code: extractedCode,
          has_source_code: Boolean(item.has_source_code || extractedCode),
          code_source: item.platform === 'github' ? 'github_sync' : 'user_upload',
          notes: ghUrl ? `GitHub: ${ghUrl}` : (item.platform === 'github' ? `GitHub File: ${item.problem_id || item.problem_title}` : ''),
          github_url: ghUrl,
        };
        setSelectedSub(standaloneSub);
      }
    } catch (err) {
      setError('Failed to load submission details.');
    }
  };

  return (
    <div style={styles.container}>
      {/* Header Banner */}
      <div className="glass-panel" style={styles.headerBanner}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Sparkles size={24} color="#818cf8" />
            <h1 style={styles.title}>Semantic Knowledge Search</h1>
          </div>
          <p style={styles.subtitle}>
            Search your indexed competitive programming submissions using natural language vector search.
          </p>
        </div>

        <button
          onClick={handleIndexAll}
          disabled={indexingAll}
          className="btn-primary"
          style={{ background: '#4f46e5' }}
        >
          <Database size={16} className={indexingAll ? 'spin' : ''} />
          <span>{indexingAll ? 'Indexing Code...' : 'Index All Submissions'}</span>
        </button>
      </div>

      {/* Phase 4 Retrieval Banner */}
      <div style={styles.phaseBanner}>
        <Zap size={18} color="#f59e0b" />
        <span>
          <strong>Phase 4 Retrieval Mode</strong>: Performs user-scoped vector similarity search over your local ChromaDB index. Returns matching code chunks and scores without generating LLM answers.
        </span>
      </div>

      {/* Status / Alert Messages */}
      {statusMsg && (
        <div style={styles.successAlert}>
          <CheckCircle size={16} />
          <span>{statusMsg}</span>
        </div>
      )}

      {error && (
        <div style={styles.errorAlert}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Search Input Box */}
      <form onSubmit={(e) => handleSearch(e)} style={styles.searchForm}>
        <div style={styles.inputWrapper}>
          <Search size={20} color="#9ca3af" style={styles.searchIcon} />
          <input
            type="text"
            placeholder="Search your code history (e.g., 'How did I solve tree DP?' or 'binary search')..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="input-field"
            style={styles.searchInput}
          />
        </div>
        <button type="submit" className="btn-primary" disabled={searching || !query.trim()}>
          {searching ? <RefreshCw size={16} className="spin" /> : <Search size={16} />}
          <span>{searching ? 'Searching...' : 'Search'}</span>
        </button>
      </form>

      {/* Preset Example Tags */}
      <div style={styles.examplesRow}>
        <span style={{ fontSize: '0.8rem', color: '#9ca3af' }}>Try example query:</span>
        {EXAMPLE_QUERIES.map((ex, idx) => (
          <button
            key={idx}
            type="button"
            onClick={(e) => {
              setQuery(ex);
              handleSearch(e, ex);
            }}
            style={styles.examplePill}
          >
            {ex}
          </button>
        ))}
      </div>

      {/* Search Results Display */}
      {results && (
        <div style={styles.resultsSection}>
          <div style={styles.resultsHeader}>
            <h3>
              Retrieved Results <span style={{ color: '#818cf8' }}>({results.total_results})</span>
            </h3>
            <span style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
              Query: "{results.query}"
            </span>
          </div>

          {results.results.length === 0 ? (
            <div className="glass-panel" style={styles.emptyCard}>
              <Code size={36} color="#6b7280" />
              <p style={{ marginTop: '0.75rem', color: '#9ca3af', maxWidth: '500px' }}>
                {results.message || 'No matching submission vectors found above the similarity threshold. Try indexing your submissions or broadening your query!'}
              </p>
            </div>
          ) : (
            <div style={styles.resultsGrid}>
              {results.results.map((item) => (
                <div key={item.id} className="glass-panel" style={styles.resultCard}>
                  <div style={styles.cardHeader}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.3rem' }}>
                        <h4 style={styles.cardTitle}>{item.problem_title}</h4>
                        <span
                          style={{
                            padding: '0.15rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.72rem',
                            fontWeight: '600',
                            background: item.has_source_code ? 'rgba(59, 130, 246, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            color: item.has_source_code ? '#60a5fa' : '#fbbf24',
                            border: item.has_source_code ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid rgba(245, 158, 11, 0.3)',
                          }}
                        >
                          {item.has_source_code ? 'Code Attached' : 'Metadata Only'}
                        </span>
                      </div>
                      <div style={styles.cardMeta}>
                        <span>ID: {item.problem_id || 'N/A'}</span>
                        <span>•</span>
                        <span>Platform: {item.platform}</span>
                        <span>•</span>
                        <span>Language: {item.language}</span>
                        <span>•</span>
                        <span>Chunk {item.chunk_index + 1} of {item.total_chunks}</span>
                      </div>
                    </div>

                    {(() => {
                      const pct = Math.round(item.similarity_score * 100);
                      let bg = 'rgba(16, 185, 129, 0.15)';
                      let border = '1px solid rgba(16, 185, 129, 0.3)';
                      let color = '#34d399';
                      let iconColor = '#10b981';
                      let label = `${pct}% Match`;

                      if (pct < 50) {
                        bg = 'rgba(245, 158, 11, 0.15)';
                        border = '1px solid rgba(245, 158, 11, 0.3)';
                        color = '#fbbf24';
                        iconColor = '#f59e0b';
                        label = `${pct}% Relevant`;
                      } else if (pct < 70) {
                        bg = 'rgba(99, 102, 241, 0.15)';
                        border = '1px solid rgba(99, 102, 241, 0.3)';
                        color = '#818cf8';
                        iconColor = '#818cf8';
                        label = `${pct}% Match`;
                      }

                      return (
                        <div
                          style={{
                            ...styles.scoreBadge,
                            background: bg,
                            border: border,
                            color: color,
                          }}
                        >
                          <Sparkles size={12} color={iconColor} />
                          <span>{label}</span>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Document / Chunk Snippet */}
                  <pre style={styles.codeSnippet}>
                    <code>{item.document_text}</code>
                  </pre>

                  <div style={styles.cardFooter}>
                    <button
                      onClick={() => handleOpenCodeViewer(item)}
                      className="btn-secondary"
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
                    >
                      <ExternalLink size={14} />
                      <span>View Full Submission & Code</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Code Viewer Modal */}
      <CodeViewerModal submission={selectedSub} onClose={() => setSelectedSub(null)} />
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
    fontSize: '0.88rem',
    marginTop: '0.2rem',
  },
  phaseBanner: {
    background: 'rgba(245, 158, 11, 0.1)',
    border: '1px solid rgba(245, 158, 11, 0.25)',
    color: '#fef3c7',
    padding: '0.85rem 1.25rem',
    borderRadius: '10px',
    fontSize: '0.85rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
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
  searchForm: {
    display: 'flex',
    gap: '0.75rem',
    alignItems: 'center',
  },
  inputWrapper: {
    position: 'relative',
    flex: 1,
  },
  searchIcon: {
    position: 'absolute',
    left: '1rem',
    top: '50%',
    transform: 'translateY(-50%)',
  },
  searchInput: {
    paddingLeft: '2.8rem',
    fontSize: '0.95rem',
  },
  examplesRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    flexWrap: 'wrap',
  },
  examplePill: {
    background: 'rgba(255, 255, 255, 0.04)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    color: '#a5b4fc',
    fontSize: '0.78rem',
    padding: '0.25rem 0.65rem',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  resultsSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    marginTop: '0.5rem',
  },
  resultsHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  emptyCard: {
    padding: '3rem',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  resultsGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
  },
  resultCard: {
    padding: '1.25rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: '1rem',
  },
  cardTitle: {
    fontSize: '1.1rem',
    fontWeight: '700',
    color: '#f3f4f6',
  },
  cardMeta: {
    fontSize: '0.78rem',
    color: '#9ca3af',
    display: 'flex',
    gap: '0.5rem',
    marginTop: '0.2rem',
  },
  scoreBadge: {
    background: 'rgba(16, 185, 129, 0.15)',
    border: '1px solid rgba(16, 185, 129, 0.3)',
    color: '#34d399',
    padding: '0.25rem 0.65rem',
    borderRadius: '12px',
    fontSize: '0.78rem',
    fontWeight: '600',
    display: 'flex',
    alignItems: 'center',
    gap: '0.35rem',
    whiteSpace: 'nowrap',
  },
  codeSnippet: {
    background: '#020617',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '8px',
    padding: '1rem',
    color: '#e2e8f0',
    fontFamily: 'var(--font-code)',
    fontSize: '0.82rem',
    overflowX: 'auto',
    maxHeight: '220px',
  },
  cardFooter: {
    display: 'flex',
    justifyContent: 'flex-end',
  },
};

export default SearchPage;
