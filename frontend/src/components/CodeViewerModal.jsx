import React, { useState, useEffect } from 'react';
import {
  X,
  ExternalLink,
  Clock,
  HardDrive,
  Tag,
  Code,
  Upload,
  Edit3,
  CheckCircle,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { submissionApi, vectorApi } from '../services/api';

const CodeViewerModal = ({ submission: initialSubmission, onClose, onUpdateSubmission }) => {
  if (!initialSubmission) return null;

  const [submission, setSubmission] = useState(initialSubmission);
  const [lookingUp, setLookingUp] = useState(false);
  const [lookupDone, setLookupDone] = useState(false);
  const [showImportForm, setShowImportForm] = useState(false);
  const [importMode, setImportMode] = useState('paste'); // 'paste' or 'upload'

  // Multi-solution state
  const [availableSolutions, setAvailableSolutions] = useState(initialSubmission?.available_solutions || []);
  const [activeFilePath, setActiveFilePath] = useState(initialSubmission?.filename || null);
  const [switchingSolution, setSwitchingSolution] = useState(false);

  // Form State
  const [pastedCode, setPastedCode] = useState('');
  const [selectedLanguage, setSelectedLanguage] = useState(initialSubmission.language || 'cpp');
  const [filenameInput, setFilenameInput] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  // Status State
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Check if submission currently has genuine source code
  const isGenuineCode = (sub) => {
    if (!sub || !sub.code || !sub.code.trim()) return false;
    if (sub.code.startsWith('// Source code not provided')) return false;
    if (sub.code_source === 'api_metadata') return false;
    if (sub.has_source_code === false) return false;
    return true;
  };

  const hasCode = isGenuineCode(submission);

  // Dynamic GitHub lookup and available solutions discovery
  useEffect(() => {
    setSubmission(initialSubmission);
    setShowImportForm(false);
    setErrorMsg('');
    setSuccessMsg('');
    setLookupDone(false);
    setAvailableSolutions(initialSubmission?.available_solutions || []);
    setActiveFilePath(initialSubmission?.filename || null);

    let isCancelled = false;

    if (initialSubmission) {
      const alreadyHasCode = isGenuineCode(initialSubmission);
      if (!alreadyHasCode) {
        setLookingUp(true);
      }

      submissionApi
        .getSourceCode(initialSubmission.id)
        .then((res) => {
          if (!isCancelled && res) {
            if (res.available_solutions && res.available_solutions.length > 0) {
              setAvailableSolutions(res.available_solutions);
            }
            if (res.source_code && (!alreadyHasCode || res.source_code !== initialSubmission.code)) {
              const updated = {
                ...initialSubmission,
                code: res.source_code,
                language: res.language || initialSubmission.language,
                code_source: 'github_lookup',
                notes: res.github_url ? `GitHub: ${res.github_url}` : initialSubmission.notes,
                has_source_code: true,
                github_url: res.github_url,
                filename: res.filename,
                available_solutions: res.available_solutions || [],
              };
              setSubmission(updated);
              setActiveFilePath(res.filename || res.available_solutions?.[0]?.path);
              if (onUpdateSubmission) onUpdateSubmission(updated);
            } else if (res.github_url && !initialSubmission.github_url) {
              setSubmission((prev) => ({
                ...prev,
                github_url: res.github_url,
                available_solutions: res.available_solutions || [],
              }));
            }
          }
        })
        .catch((err) => {
          console.log('GitHub lookup detail:', err.response?.data?.detail || err.message);
        })
        .finally(() => {
          if (!isCancelled) {
            setLookingUp(false);
            setLookupDone(true);
          }
        });

      return () => {
        isCancelled = true;
      };
    }
  }, [initialSubmission?.id]);

  // Handle switching to a specific solution file
  const handleSelectSolution = async (solution) => {
    if (!solution || !solution.path || solution.path === activeFilePath) return;
    setSwitchingSolution(true);
    setErrorMsg('');
    try {
      const res = await submissionApi.getSourceCode(submission.id, solution.path);
      if (res && res.source_code) {
        setActiveFilePath(solution.path);
        setSubmission((prev) => ({
          ...prev,
          code: res.source_code,
          language: res.language,
          filename: res.filename,
          github_url: res.github_url,
        }));
      }
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to load selected solution file.');
    } finally {
      setSwitchingSolution(false);
    }
  };

  // Extract GitHub URL from notes or direct property
  const githubUrl =
    submission.github_url ||
    (submission.notes && submission.notes.startsWith('GitHub: ')
      ? submission.notes.replace(/^GitHub:\s*/, '').trim()
      : null);

  // Save pasted code
  const handleSavePastedCode = async (e) => {
    e.preventDefault();
    if (!pastedCode.trim()) {
      setErrorMsg('Source code text cannot be empty.');
      return;
    }
    setSaving(true);
    setErrorMsg('');
    setSuccessMsg('');

    try {
      const res = await submissionApi.addSourceCode(
        submission.id,
        pastedCode.trim(),
        selectedLanguage,
        filenameInput.trim() || undefined
      );

      const updated = {
        ...submission,
        code: res.source_code,
        code_source: 'user_upload',
        language: res.language,
        filename: res.filename,
        has_source_code: true,
      };

      setSubmission(updated);
      if (onUpdateSubmission) onUpdateSubmission(updated);

      setSuccessMsg('Source code attached & indexed for Knowledge Base successfully!');
      setShowImportForm(false);
      setPastedCode('');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to attach source code.';
      setErrorMsg(msg);
    } finally {
      setSaving(false);
    }
  };

  // Upload source code file
  const handleUploadFile = async (e) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMsg('Please select a source code file.');
      return;
    }
    setSaving(true);
    setErrorMsg('');
    setSuccessMsg('');

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('language', selectedLanguage);

      const res = await submissionApi.uploadSourceCodeFile(submission.id, formData);

      const updated = {
        ...submission,
        code: res.source_code,
        code_source: 'user_upload',
        language: res.language,
        filename: res.filename,
        has_source_code: true,
      };

      setSubmission(updated);
      if (onUpdateSubmission) onUpdateSubmission(updated);

      setSuccessMsg(`Uploaded '${res.filename}' & indexed for Knowledge Base successfully!`);
      setShowImportForm(false);
      setSelectedFile(null);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to upload source code file.';
      setErrorMsg(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div style={styles.header}>
          <div>
            <div style={styles.titleRow}>
              <h2 style={styles.problemTitle}>{submission.problem_title}</h2>
              <span className="badge badge-platform">{submission.platform}</span>
              <span
                className={`badge ${
                  submission.verdict === 'ACCEPTED' ? 'badge-accepted' : 'badge-wrong'
                }`}
              >
                {submission.verdict}
              </span>
              <span
                style={{
                  padding: '0.2rem 0.6rem',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  fontWeight: '600',
                  background: hasCode
                    ? submission.code_source === 'github_lookup'
                      ? 'rgba(129, 140, 248, 0.15)'
                      : 'rgba(16, 185, 129, 0.15)'
                    : lookingUp
                    ? 'rgba(99, 102, 241, 0.15)'
                    : 'rgba(245, 158, 11, 0.15)',
                  color: hasCode
                    ? submission.code_source === 'github_lookup'
                      ? '#a5b4fc'
                      : '#34d399'
                    : lookingUp
                    ? '#818cf8'
                    : '#fbbf24',
                  border: hasCode
                    ? submission.code_source === 'github_lookup'
                      ? '1px solid rgba(129, 140, 248, 0.3)'
                      : '1px solid rgba(16, 185, 129, 0.3)'
                    : lookingUp
                    ? '1px solid rgba(99, 102, 241, 0.3)'
                    : '1px solid rgba(245, 158, 11, 0.3)',
                }}
              >
                {hasCode
                  ? submission.code_source === 'github_lookup'
                    ? 'GitHub Linked'
                    : 'Source Code Attached'
                  : lookingUp
                  ? 'Searching GitHub...'
                  : 'Source Code Unavailable'}
              </span>
            </div>
            <div style={styles.metaRow}>
              <span>ID: {submission.problem_id}</span>
              <span>•</span>
              <span>Language: {submission.language}</span>
              <span>•</span>
              {submission.difficulty && <span>Rating: {submission.difficulty}</span>}
            </div>
          </div>
          <button onClick={onClose} style={styles.closeBtn}>
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={styles.body}>
          {successMsg && (
            <div style={styles.successAlert}>
              <CheckCircle size={16} />
              <span>{successMsg}</span>
            </div>
          )}

          {errorMsg && (
            <div style={styles.errorAlert}>
              <AlertCircle size={16} />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Looking Up Banner */}
          {lookingUp && (
            <div style={styles.lookingUpCard}>
              <RefreshCw size={18} className="spin" color="#818cf8" style={{ flexShrink: 0 }} />
              <div>
                <div style={{ fontWeight: '600', color: '#c7d2fe', fontSize: '0.85rem' }}>
                  Looking up solution in connected GitHub repository...
                </div>
                <div style={{ color: '#9ca3af', fontSize: '0.78rem', marginTop: '0.15rem' }}>
                  Searching repository tree and matching by problem title, slug, and filename.
                </div>
              </div>
            </div>
          )}

          {/* Source Code Unavailable Alert */}
          {!hasCode && !lookingUp && (
            <div style={styles.metadataWarningBox}>
              <AlertCircle size={20} color="#f59e0b" style={{ flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: '700', color: '#fbbf24', fontSize: '0.88rem' }}>
                  Source Code Unavailable
                </div>
                <div style={{ color: '#d1d5db', fontSize: '0.8rem', marginTop: '0.2rem' }}>
                  {submission.platform === 'leetcode'
                    ? 'No matching solution file was found in your connected GitHub repository. Attach your source code below so the AI Knowledge Base can analyze your implementation.'
                    : 'Source code was not provided for this submission. Attach your source code below so the AI Knowledge Base can search and analyze it.'}
                </div>
              </div>
              <button
                onClick={() => setShowImportForm(true)}
                className="btn-primary"
                style={{
                  padding: '0.35rem 0.75rem',
                  fontSize: '0.8rem',
                  background: '#f59e0b',
                  color: '#0f172a',
                  border: 'none',
                }}
              >
                <Edit3 size={14} />
                <span>Attach Source Code</span>
              </button>
            </div>
          )}

          {/* Metadata Cards */}
          <div style={styles.statsGrid}>
            <div style={styles.statBox}>
              <Clock size={16} color="#9ca3af" />
              <div>
                <div style={styles.statLabel}>Execution Time</div>
                <div style={styles.statVal}>
                  {submission.execution_time_ms !== null ? `${submission.execution_time_ms} ms` : 'N/A'}
                </div>
              </div>
            </div>

            <div style={styles.statBox}>
              <HardDrive size={16} color="#9ca3af" />
              <div>
                <div style={styles.statLabel}>Memory Used</div>
                <div style={styles.statVal}>
                  {submission.memory_bytes
                    ? `${(submission.memory_bytes / 1024 / 1024).toFixed(2)} MB`
                    : 'N/A'}
                </div>
              </div>
            </div>

            <div style={styles.statBox}>
              <ExternalLink size={16} color="#6366f1" />
              <div>
                <div style={styles.statLabel}>Problem Link</div>
                <a
                  href={submission.problem_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={styles.link}
                >
                  View Statement
                </a>
              </div>
            </div>
          </div>

          {/* Tags */}
          {submission.tags && submission.tags.length > 0 && (
            <div style={styles.tagsRow}>
              <Tag size={14} color="#9ca3af" />
              <span style={{ fontSize: '0.8rem', color: '#9ca3af' }}>Tags:</span>
              {submission.tags.map((tag, idx) => (
                <span key={idx} style={styles.tagPill}>
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Code Viewer Header */}
          <div style={styles.codeHeader}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Code size={16} color="#6366f1" />
              <span style={{ fontWeight: '600', fontSize: '0.9rem' }}>Source Code</span>
              {hasCode && (
                <span style={{ fontSize: '0.75rem', color: '#818cf8', background: 'rgba(99,102,241,0.1)', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
                  {submission.language}
                </span>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
              <span style={styles.sourceTag}>
                Source: {hasCode ? submission.code_source : 'unavailable'}
              </span>

              {githubUrl && (
                <a
                  href={githubUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={styles.githubLink}
                  title="View original solution file on GitHub"
                >
                  <ExternalLink size={13} />
                  <span>View on GitHub</span>
                </a>
              )}

              {hasCode && (
                <button
                  onClick={async () => {
                    setSaving(true);
                    setErrorMsg('');
                    setSuccessMsg('');
                    try {
                      const res = await vectorApi.indexSubmission(submission.id);
                      setSuccessMsg(res.message);
                    } catch (err) {
                      const msg = err.response?.data?.detail || 'Failed to index submission.';
                      setErrorMsg(msg);
                    } finally {
                      setSaving(false);
                    }
                  }}
                  className="btn-primary"
                  disabled={saving}
                  style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', background: '#4f46e5' }}
                >
                  <Tag size={14} />
                  <span>{saving ? 'Indexing...' : 'Index for Knowledge Base'}</span>
                </button>
              )}

              <button
                onClick={() => setShowImportForm(!showImportForm)}
                className="btn-secondary"
                style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem' }}
              >
                <Edit3 size={14} />
                <span>{showImportForm ? 'Cancel' : hasCode ? 'Update Code' : 'Attach Code'}</span>
              </button>
            </div>
          </div>

          {/* Source Code Import Form */}
          {showImportForm && (
            <div style={styles.importCard}>
              <div style={styles.importTabHeader}>
                <button
                  onClick={() => setImportMode('paste')}
                  style={{
                    ...styles.tabBtn,
                    ...(importMode === 'paste' ? styles.tabBtnActive : {}),
                  }}
                >
                  <Edit3 size={14} /> Paste Code
                </button>
                <button
                  onClick={() => setImportMode('upload')}
                  style={{
                    ...styles.tabBtn,
                    ...(importMode === 'upload' ? styles.tabBtnActive : {}),
                  }}
                >
                  <Upload size={14} /> Upload File (.cpp, .py, .java, etc.)
                </button>
              </div>

              {importMode === 'paste' ? (
                <form onSubmit={handleSavePastedCode} style={styles.importForm}>
                  <div style={styles.formRow}>
                    <select
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      style={styles.select}
                    >
                      <option value="cpp">C++ (cpp)</option>
                      <option value="python">Python (python)</option>
                      <option value="java">Java (java)</option>
                      <option value="javascript">JavaScript (js)</option>
                      <option value="typescript">TypeScript (ts)</option>
                    </select>

                    <input
                      type="text"
                      placeholder="Optional filename (e.g. solution.cpp)"
                      value={filenameInput}
                      onChange={(e) => setFilenameInput(e.target.value)}
                      className="input-field"
                    />
                  </div>

                  <textarea
                    rows={8}
                    placeholder="Paste your source code here..."
                    value={pastedCode}
                    onChange={(e) => setPastedCode(e.target.value)}
                    className="input-field"
                    style={{ fontFamily: 'var(--font-code)', fontSize: '0.85rem' }}
                  />

                  <button type="submit" className="btn-primary" disabled={saving}>
                    {saving ? 'Saving...' : 'Save Source Code'}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleUploadFile} style={styles.importForm}>
                  <div style={styles.formRow}>
                    <select
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      style={styles.select}
                    >
                      <option value="cpp">C++ (.cpp, .cc)</option>
                      <option value="python">Python (.py)</option>
                      <option value="java">Java (.java)</option>
                      <option value="javascript">JavaScript (.js)</option>
                      <option value="typescript">TypeScript (.ts)</option>
                    </select>
                  </div>

                  <input
                    type="file"
                    accept=".cpp,.cc,.cxx,.c,.java,.py,.js,.ts"
                    onChange={(e) => setSelectedFile(e.target.files[0])}
                    className="input-field"
                  />

                  <button type="submit" className="btn-primary" disabled={saving}>
                    {saving ? 'Uploading...' : 'Upload File'}
                  </button>
                </form>
              )}
            </div>
          )}

          {/* Multi-Solution Switcher */}
          {availableSolutions && availableSolutions.length > 1 && (
            <div style={styles.solutionSwitcherBar}>
              <span style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: '600' }}>
                Available Solutions ({availableSolutions.length}):
              </span>
              <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                {availableSolutions.map((sol, idx) => {
                  const isActive =
                    activeFilePath === sol.path ||
                    activeFilePath === sol.filename ||
                    (!activeFilePath && idx === 0);
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSelectSolution(sol)}
                      disabled={switchingSolution}
                      style={{
                        padding: '0.25rem 0.65rem',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: '600',
                        cursor: 'pointer',
                        border: isActive ? '1px solid #6366f1' : '1px solid rgba(255, 255, 255, 0.1)',
                        background: isActive ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                        color: isActive ? '#a5b4fc' : '#9ca3af',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.35rem',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <span>{sol.filename}</span>
                      <span style={{ opacity: 0.75, fontSize: '0.7rem' }}>({sol.language})</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Code Viewer Block or State Box */}
          {hasCode ? (
            <pre style={styles.codeBlock}>
              <code>{submission.code}</code>
            </pre>
          ) : lookingUp ? (
            <div style={styles.emptyCodeBox}>
              <RefreshCw size={28} className="spin" color="#818cf8" />
              <div style={{ color: '#c7d2fe', fontSize: '0.88rem', fontWeight: '600', marginTop: '0.75rem' }}>
                Searching GitHub for matching solution...
              </div>
              <p style={{ color: '#9ca3af', fontSize: '0.78rem', marginTop: '0.25rem' }}>
                Querying repository structure and solution files
              </p>
            </div>
          ) : (
            <div style={styles.emptyCodeBox}>
              <AlertCircle size={32} color="#64748b" />
              <div style={{ color: '#94a3b8', fontSize: '0.9rem', fontWeight: '600', marginTop: '0.6rem' }}>
                Source Code Unavailable
              </div>
              <p style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.25rem', textAlign: 'center', maxWidth: '420px', lineHeight: 1.5 }}>
                No genuine source code was found in your connected GitHub repository for this problem. You can manually attach or paste your solution using the button above.
              </p>
            </div>
          )}

          {submission.notes && (
            <div style={styles.notesBox}>
              <strong>Solution Note:</strong> {submission.notes}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const styles = {
  overlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    backdropFilter: 'blur(4px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 50,
    padding: '1.5rem',
  },
  modal: {
    width: '100%',
    maxWidth: '840px',
    maxHeight: '90vh',
    backgroundColor: '#0f172a',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '16px',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: '0 20px 50px rgba(0, 0, 0, 0.5)',
  },
  header: {
    padding: '1.25rem 1.5rem',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    background: '#1e293b',
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    flexWrap: 'wrap',
  },
  problemTitle: {
    fontSize: '1.25rem',
    fontWeight: '700',
    color: '#f9fafb',
  },
  metaRow: {
    fontSize: '0.8rem',
    color: '#9ca3af',
    display: 'flex',
    gap: '0.5rem',
    marginTop: '0.3rem',
  },
  closeBtn: {
    background: 'transparent',
    border: 'none',
    color: '#9ca3af',
    cursor: 'pointer',
    padding: '0.2rem',
  },
  body: {
    padding: '1.25rem 1.5rem',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
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
  lookingUpCard: {
    background: 'rgba(99, 102, 241, 0.12)',
    border: '1px solid rgba(99, 102, 241, 0.25)',
    borderRadius: '10px',
    padding: '0.85rem 1rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.85rem',
  },
  metadataWarningBox: {
    background: 'rgba(245, 158, 11, 0.12)',
    border: '1px solid rgba(245, 158, 11, 0.3)',
    borderRadius: '10px',
    padding: '0.85rem 1rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.85rem',
    flexWrap: 'wrap',
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
    gap: '1rem',
  },
  statBox: {
    background: 'rgba(255, 255, 255, 0.03)',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    borderRadius: '8px',
    padding: '0.75rem 1rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  statLabel: {
    fontSize: '0.7rem',
    color: '#9ca3af',
  },
  statVal: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#f3f4f6',
  },
  link: {
    color: '#818cf8',
    textDecoration: 'none',
    fontSize: '0.85rem',
    fontWeight: '600',
  },
  tagsRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    flexWrap: 'wrap',
  },
  tagPill: {
    background: 'rgba(99, 102, 241, 0.1)',
    color: '#a5b4fc',
    border: '1px solid rgba(99, 102, 241, 0.2)',
    fontSize: '0.75rem',
    padding: '0.15rem 0.5rem',
    borderRadius: '4px',
  },
  codeHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    color: '#f3f4f6',
    flexWrap: 'wrap',
    gap: '0.5rem',
  },
  sourceTag: {
    fontSize: '0.75rem',
    color: '#9ca3af',
    background: '#1e293b',
    padding: '0.25rem 0.6rem',
    borderRadius: '4px',
  },
  githubLink: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.35rem',
    fontSize: '0.8rem',
    color: '#a5b4fc',
    background: 'rgba(99, 102, 241, 0.15)',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    padding: '0.25rem 0.6rem',
    borderRadius: '4px',
    textDecoration: 'none',
    fontWeight: '600',
    transition: 'all 0.15s ease',
  },
  importCard: {
    background: '#1e293b',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    borderRadius: '10px',
    padding: '1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.85rem',
  },
  importTabHeader: {
    display: 'flex',
    gap: '0.5rem',
  },
  tabBtn: {
    padding: '0.4rem 0.8rem',
    borderRadius: '6px',
    border: 'none',
    background: 'rgba(255, 255, 255, 0.05)',
    color: '#9ca3af',
    fontSize: '0.8rem',
    fontWeight: '600',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
  },
  tabBtnActive: {
    background: 'rgba(99, 102, 241, 0.2)',
    color: '#a5b4fc',
    border: '1px solid rgba(99, 102, 241, 0.4)',
  },
  importForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  formRow: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '0.75rem',
  },
  select: {
    background: '#0f172a',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    color: '#f3f4f6',
    borderRadius: '6px',
    padding: '0.6rem',
    fontSize: '0.85rem',
  },
  codeBlock: {
    background: '#020617',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '8px',
    padding: '1rem',
    color: '#e2e8f0',
    fontFamily: 'var(--font-code)',
    fontSize: '0.85rem',
    overflowX: 'auto',
    maxHeight: '340px',
  },
  emptyCodeBox: {
    background: '#020617',
    border: '1px dashed rgba(255, 255, 255, 0.1)',
    borderRadius: '8px',
    padding: '2.5rem 1.5rem',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '180px',
  },
  solutionSwitcherBar: {
    background: '#1e293b',
    border: '1px solid rgba(99, 102, 241, 0.2)',
    borderRadius: '8px',
    padding: '0.5rem 0.75rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    flexWrap: 'wrap',
  },
  notesBox: {
    background: 'rgba(245, 158, 11, 0.1)',
    border: '1px solid rgba(245, 158, 11, 0.2)',
    color: '#fef3c7',
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    fontSize: '0.85rem',
  },
};

export default CodeViewerModal;
