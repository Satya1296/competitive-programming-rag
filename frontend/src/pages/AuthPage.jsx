import React, { useState } from 'react';
import { Terminal, Shield, Cpu, Lock, User, Mail, ArrowRight, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const AuthPage = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login, register } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!isLogin) {
      if (!email.trim() || !username.trim() || !password) {
        setError('Please fill in all registration fields.');
        return;
      }
      if (username.trim().length < 3) {
        setError('Username must be at least 3 characters long.');
        return;
      }
      if (password.length < 6) {
        setError('Password must be at least 6 characters long.');
        return;
      }
    }

    setLoading(true);

    try {
      if (isLogin) {
        await login(username.trim() || email.trim(), password);
      } else {
        await register(email.trim(), username.trim(), password);
      }
    } catch (err) {
      let msg = err.response?.data?.detail;
      if (Array.isArray(msg)) {
        msg = msg.map((m) => m.msg || m.message || (typeof m === 'string' ? m : JSON.stringify(m))).join(', ');
      } else if (typeof msg === 'object' && msg !== null) {
        msg = msg.message || msg.msg || JSON.stringify(msg);
      }
      if (!msg) {
        msg = err.message || 'Authentication failed.';
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      {/* Background Decorative Glow */}
      <div style={styles.glowTop} />
      <div style={styles.glowBottom} />

      <div style={styles.wrapper}>
        {/* Left Column: Project Description */}
        <div style={styles.heroSection}>
          <div style={styles.logoRow}>
            <div style={styles.logoBox}>
              <Terminal size={28} color="#6366f1" />
            </div>
            <span style={styles.logoText}>CP Knowledge RAG</span>
          </div>

          <h1 style={styles.heroTitle}>
            Competitive Programming <br />
            <span style={styles.heroGradient}>Knowledge Retrieval System</span>
          </h1>

          <p style={styles.heroDesc}>
            A Retrieval-Augmented Generation (RAG) platform that indexes your competitive programming submission history across 
            <strong> Codeforces, LeetCode, and CodeChef</strong> into a multi-user vector database for instant semantic code retrieval and AI problem analysis.
          </p>

          <div style={styles.featureGrid}>
            <div style={styles.featureCard}>
              <Cpu size={20} color="#6366f1" />
              <div>
                <h4 style={styles.featureTitle}>Multi-User Isolation</h4>
                <p style={styles.featureText}>Your submissions & RAG vectors are strictly private and isolated.</p>
              </div>
            </div>

            <div style={styles.featureCard}>
              <Shield size={20} color="#06b6d4" />
              <div>
                <h4 style={styles.featureTitle}>Automated Profile Sync</h4>
                <p style={styles.featureText}>Connect your Codeforces handle to fetch metadata & track solutions.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Auth Form Card */}
        <div className="glass-panel" style={styles.authCard}>
          {/* Tab Selector */}
          <div style={styles.tabHeader}>
            <button
              onClick={() => { setIsLogin(true); setError(''); }}
              style={{ ...styles.tabBtn, ...(isLogin ? styles.tabBtnActive : {}) }}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsLogin(false); setError(''); }}
              style={{ ...styles.tabBtn, ...(!isLogin ? styles.tabBtnActive : {}) }}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleSubmit} style={styles.form}>
            {error && (
              <div style={styles.errorAlert}>
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}

            {!isLogin && (
              <div style={styles.inputGroup}>
                <label style={styles.label}>Email Address</label>
                <div style={styles.inputWrapper}>
                  <Mail size={16} color="#9ca3af" style={styles.inputIcon} />
                  <input
                    type="email"
                    placeholder="user@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required={!isLogin}
                    className="input-field"
                    style={{ paddingLeft: '2.5rem' }}
                  />
                </div>
              </div>
            )}

            <div style={styles.inputGroup}>
              <label style={styles.label}>{isLogin ? 'Email or Username' : 'Username'}</label>
              <div style={styles.inputWrapper}>
                <User size={16} color="#9ca3af" style={styles.inputIcon} />
                <input
                  type="text"
                  placeholder={isLogin ? 'tourist or user@example.com' : 'tourist'}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  className="input-field"
                  style={{ paddingLeft: '2.5rem' }}
                />
              </div>
            </div>

            <div style={styles.inputGroup}>
              <label style={styles.label}>Password</label>
              <div style={styles.inputWrapper}>
                <Lock size={16} color="#9ca3af" style={styles.inputIcon} />
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="input-field"
                  style={{ paddingLeft: '2.5rem' }}
                />
              </div>
            </div>

            <button type="submit" className="btn-primary" disabled={loading} style={styles.submitBtn}>
              {loading ? (
                'Processing...'
              ) : (
                <>
                  <span>{isLogin ? 'Sign In to Dashboard' : 'Register Account'}</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
    position: 'relative',
    backgroundColor: '#0b0f19',
    overflow: 'hidden',
  },
  glowTop: {
    position: 'absolute',
    top: '-20%',
    left: '10%',
    width: '500px',
    height: '500px',
    background: 'radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, rgba(0,0,0,0) 70%)',
    pointerEvents: 'none',
  },
  glowBottom: {
    position: 'absolute',
    bottom: '-20%',
    right: '10%',
    width: '500px',
    height: '500px',
    background: 'radial-gradient(circle, rgba(6, 182, 212, 0.15) 0%, rgba(0,0,0,0) 70%)',
    pointerEvents: 'none',
  },
  wrapper: {
    maxWidth: '1100px',
    width: '100%',
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
    gap: '3rem',
    alignItems: 'center',
    zIndex: 10,
  },
  heroSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
  },
  logoRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  logoBox: {
    width: '44px',
    height: '44px',
    borderRadius: '12px',
    background: 'rgba(99, 102, 241, 0.15)',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoText: {
    fontSize: '1rem',
    fontWeight: '700',
    color: '#a5b4fc',
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
  },
  heroTitle: {
    fontSize: '2.5rem',
    fontWeight: '800',
    lineHeight: 1.15,
    color: '#f9fafb',
  },
  heroGradient: {
    background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  heroDesc: {
    color: '#9ca3af',
    fontSize: '1rem',
    lineHeight: 1.6,
  },
  featureGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    marginTop: '1rem',
  },
  featureCard: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.75rem',
    background: 'rgba(255, 255, 255, 0.03)',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    padding: '0.85rem 1rem',
    borderRadius: '10px',
  },
  featureTitle: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#f3f4f6',
  },
  featureText: {
    fontSize: '0.8rem',
    color: '#6b7280',
  },
  authCard: {
    padding: '2rem',
  },
  tabHeader: {
    display: 'flex',
    background: 'rgba(15, 23, 42, 0.6)',
    padding: '0.25rem',
    borderRadius: '8px',
    marginBottom: '1.5rem',
  },
  tabBtn: {
    flex: 1,
    padding: '0.6rem',
    background: 'transparent',
    border: 'none',
    color: '#9ca3af',
    fontWeight: '600',
    fontSize: '0.9rem',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  tabBtnActive: {
    background: '#1e293b',
    color: '#f9fafb',
    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.2rem',
  },
  errorAlert: {
    background: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    color: '#f87171',
    padding: '0.75rem 1rem',
    borderRadius: '8px',
    fontSize: '0.85rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.4rem',
  },
  label: {
    fontSize: '0.85rem',
    fontWeight: '500',
    color: '#cbd5e1',
  },
  inputWrapper: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },
  inputIcon: {
    position: 'absolute',
    left: '0.85rem',
    pointerEvents: 'none',
  },
  submitBtn: {
    width: '100%',
    justifyContent: 'center',
    padding: '0.85rem',
    fontSize: '1rem',
    marginTop: '0.5rem',
  },
};

export default AuthPage;
