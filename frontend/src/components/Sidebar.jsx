import React from 'react';
import {
  LayoutDashboard,
  UserCheck,
  Database,
  MessageSquareCode,
  LogOut,
  Terminal,
  Search,
  Users,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Sidebar = ({ activeTab, setActiveTab }) => {
  const { logout, user } = useAuth();

  const personalItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'profiles', label: 'My Profiles', icon: UserCheck },
    { id: 'submissions', label: 'My Submissions', icon: Database },
    { id: 'search', label: 'Semantic Search', icon: Search },
    { id: 'chat', label: 'Knowledge Chat', icon: MessageSquareCode },
  ];

  const externalItems = [
    { id: 'public-search', label: 'Friends / Public Profiles', icon: Users },
  ];

  return (
    <aside style={styles.sidebar}>
      {/* Brand Header */}
      <div style={styles.brand}>
        <div style={styles.logoBadge}>
          <Terminal size={22} color="#6366f1" />
        </div>
        <div>
          <h2 style={styles.brandTitle}>CP Retrieval</h2>
          <p style={styles.brandSubtitle}>Knowledge System</p>
        </div>
      </div>

      {/* Navigation Sections */}
      <nav style={styles.nav}>
        <div style={styles.sectionHeader}>PERSONAL KNOWLEDGE SYSTEM</div>
        {personalItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              style={{
                ...styles.navItem,
                ...(isActive ? styles.navItemActive : {}),
              }}
            >
              <Icon size={18} color={isActive ? '#6366f1' : '#9ca3af'} />
              <span>{item.label}</span>
              {item.id === 'search' && (
                <span style={{ ...styles.betaTag, background: 'linear-gradient(135deg, #6366f1, #06b6d4)' }}>
                  Vector
                </span>
              )}
              {item.id === 'chat' && (
                <span style={styles.betaTag}>RAG</span>
              )}
            </button>
          );
        })}

        <div style={{ ...styles.sectionHeader, marginTop: '1.25rem' }}>EXTERNAL / PUBLIC</div>
        {externalItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              style={{
                ...styles.navItem,
                ...(isActive ? styles.navItemActive : {}),
              }}
            >
              <Icon size={18} color={isActive ? '#6366f1' : '#9ca3af'} />
              <span>{item.label}</span>
              <span style={{ ...styles.betaTag, background: 'linear-gradient(135deg, #10b981, #06b6d4)' }}>
                Public
              </span>
            </button>
          );
        })}
      </nav>

      {/* User Footer & Logout */}
      <div style={styles.footer}>
        <div style={styles.userInfo}>
          <div style={styles.avatar}>
            {user?.username?.substring(0, 2).toUpperCase() || 'CP'}
          </div>
          <div style={{ overflow: 'hidden' }}>
            <div style={styles.userName}>{user?.username || 'User'}</div>
            <div style={styles.userEmail}>{user?.email}</div>
          </div>
        </div>
        <button onClick={logout} style={styles.logoutBtn} title="Sign Out">
          <LogOut size={16} />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
};

const styles = {
  sidebar: {
    width: '260px',
    backgroundColor: '#0f172a',
    borderRight: '1px solid rgba(255, 255, 255, 0.08)',
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    position: 'sticky',
    top: 0,
    padding: '1.25rem 1rem',
    zIndex: 20,
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    paddingBottom: '1.25rem',
    marginBottom: '1rem',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  },
  logoBadge: {
    width: '40px',
    height: '40px',
    borderRadius: '10px',
    background: 'rgba(99, 102, 241, 0.15)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px solid rgba(99, 102, 241, 0.3)',
  },
  brandTitle: {
    fontSize: '1.1rem',
    fontWeight: '700',
    color: '#f9fafb',
    lineHeight: 1.2,
  },
  brandSubtitle: {
    fontSize: '0.75rem',
    color: '#9ca3af',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.4rem',
    flex: 1,
  },
  sectionHeader: {
    fontSize: '0.68rem',
    fontWeight: '700',
    color: '#64748b',
    letterSpacing: '0.08em',
    padding: '0.4rem 0.5rem',
    marginBottom: '0.2rem',
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.7rem 0.85rem',
    borderRadius: '8px',
    backgroundColor: 'transparent',
    color: '#9ca3af',
    border: 'none',
    cursor: 'pointer',
    fontSize: '0.88rem',
    fontWeight: '500',
    textAlign: 'left',
    transition: 'all 0.2s ease',
  },
  navItemActive: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    color: '#f9fafb',
    borderLeft: '3px solid #6366f1',
    fontWeight: '600',
  },
  betaTag: {
    marginLeft: 'auto',
    fontSize: '0.65rem',
    fontWeight: '700',
    padding: '0.15rem 0.4rem',
    borderRadius: '4px',
    background: 'linear-gradient(135deg, #ec4899, #8b5cf6)',
    color: '#fff',
  },
  footer: {
    paddingTop: '1rem',
    borderTop: '1px solid rgba(255, 255, 255, 0.08)',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
  },
  userInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.65rem',
  },
  avatar: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
    color: '#fff',
    fontWeight: '700',
    fontSize: '0.85rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  userName: {
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#f3f4f6',
    whiteSpace: 'nowrap',
    textOverflow: 'ellipsis',
    overflow: 'hidden',
  },
  userEmail: {
    fontSize: '0.7rem',
    color: '#6b7280',
    whiteSpace: 'nowrap',
    textOverflow: 'ellipsis',
    overflow: 'hidden',
  },
  logoutBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    width: '100%',
    padding: '0.5rem',
    borderRadius: '6px',
    background: 'rgba(239, 68, 68, 0.1)',
    color: '#f87171',
    border: '1px solid rgba(239, 68, 68, 0.2)',
    fontSize: '0.8rem',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
};

export default Sidebar;
