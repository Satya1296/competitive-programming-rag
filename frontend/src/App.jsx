import React, { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { platformApi } from './services/api';
import AuthPage from './pages/AuthPage';
import DashboardPage from './pages/DashboardPage';
import MyProfilesPage from './pages/MyProfilesPage';
import SubmissionsPage from './pages/SubmissionsPage';
import SearchPage from './pages/SearchPage';
import ChatPage from './pages/ChatPage';
import PublicProfilesPage from './pages/PublicProfilesPage';
import OnboardingPage from './pages/OnboardingPage';
import Sidebar from './components/Sidebar';

const MainApp = () => {
  const { user, loading } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [checkingProfiles, setCheckingProfiles] = useState(true);

  useEffect(() => {
    let isMounted = true;
    const checkUserOnboarding = async () => {
      if (!user) {
        setShowOnboarding(false);
        setCheckingProfiles(false);
        return;
      }
      if (isMounted) setCheckingProfiles(true);
      try {
        const statuses = await platformApi.getAllStatuses();
        // If user has 0 connected profiles, show onboarding once
        if (isMounted && (!statuses || statuses.length === 0)) {
          setShowOnboarding(true);
        } else if (isMounted) {
          setShowOnboarding(false);
        }
      } catch (err) {
        console.error('Failed to check user profiles for onboarding:', err);
        if (isMounted) setShowOnboarding(false);
      } finally {
        if (isMounted) setCheckingProfiles(false);
      }
    };

    checkUserOnboarding();
    return () => {
      isMounted = false;
    };
  }, [user]);

  if (loading || checkingProfiles) {
    return (
      <div style={styles.fullLoader}>
        <div style={styles.spinner} />
        <p style={{ color: '#9ca3af', marginTop: '1rem' }}>Loading application session...</p>
      </div>
    );
  }

  if (!user) {
    return <AuthPage />;
  }

  if (showOnboarding) {
    return <OnboardingPage onComplete={() => setShowOnboarding(false)} />;
  }

  return (
    <div style={styles.layout}>
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <main style={styles.mainContent}>
        {activeTab === 'dashboard' && <DashboardPage />}
        {activeTab === 'profiles' && <MyProfilesPage />}
        {activeTab === 'submissions' && <SubmissionsPage />}
        {activeTab === 'search' && <SearchPage />}
        {activeTab === 'chat' && <ChatPage />}
        {activeTab === 'public-search' && <PublicProfilesPage />}
      </main>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}

const styles = {
  fullLoader: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#0b0f19',
  },
  spinner: {
    width: '40px',
    height: '40px',
    border: '4px solid rgba(99, 102, 241, 0.2)',
    borderTopColor: '#6366f1',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  layout: {
    display: 'flex',
    minHeight: '100vh',
    backgroundColor: '#0b0f19',
  },
  mainContent: {
    flex: 1,
    overflowY: 'auto',
    backgroundColor: '#0b0f19',
  },
};

export default App;
