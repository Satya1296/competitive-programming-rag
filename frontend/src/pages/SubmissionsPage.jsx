import React, { useState, useEffect } from 'react';
import { submissionApi } from '../services/api';
import SubmissionsTable from '../components/SubmissionsTable';
import CodeViewerModal from '../components/CodeViewerModal';
import { Database, Download } from 'lucide-react';

const SubmissionsPage = () => {
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedSub, setSelectedSub] = useState(null);

  const fetchSubmissions = async () => {
    setLoading(true);
    try {
      const data = await submissionApi.getSubmissions({ limit: 500 });
      setSubmissions(data);
    } catch (err) {
      setError('Failed to fetch user submissions.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSubmissions();
  }, []);

  const handleUpdateSubmission = (updatedSub) => {
    setSubmissions((prev) =>
      prev.map((s) => (s.id === updatedSub.id ? { ...s, ...updatedSub } : s))
    );
    setSelectedSub(updatedSub);
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Database size={24} color="#6366f1" />
            <h1 style={styles.title}>Submissions Explorer</h1>
          </div>
          <p style={styles.subtitle}>
            Browse, search, and filter your user-scoped competitive programming history.
          </p>
        </div>
      </div>

      {/* Submissions Table */}
      <SubmissionsTable
        submissions={submissions}
        onSelectSubmission={(sub) => setSelectedSub(sub)}
        loading={loading}
        error={error}
      />

      {/* Code Viewer Modal */}
      <CodeViewerModal
        submission={selectedSub}
        onClose={() => setSelectedSub(null)}
        onUpdateSubmission={handleUpdateSubmission}
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
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
  },
  title: {
    fontSize: '1.6rem',
    fontWeight: '800',
    color: '#f9fafb',
  },
  subtitle: {
    fontSize: '0.9rem',
    color: '#9ca3af',
    marginTop: '0.2rem',
  },
};

export default SubmissionsPage;
