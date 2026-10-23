import React, { useState } from 'react';
import { MessageSquareCode, Send, Sparkles, Bot, User as UserIcon, RefreshCw } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ragApi } from '../services/api';

const SAMPLE_QUESTIONS = [
  'How did I approach binary search?',
  'What mistakes do I make in graph problems?',
  'How can I improve my greedy solutions?',
  'What is my approach to prefix sums?',
];

const ChatPage = () => {
  const { user } = useAuth();
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'assistant',
      text: `Hello ${user?.username || 'there'}! I am your Personal Coding Mentor. Ask me about any coding concept to review your actual approach, identify mistakes, and get next steps.`,
      sources: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSend = async (e, customQuery = null) => {
    if (e) e.preventDefault();
    const queryText = customQuery || inputQuery;
    if (!queryText.trim() || loading) return;

    const userTimestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const userMessage = {
      id: Date.now(),
      sender: 'user',
      text: queryText.trim(),
      timestamp: userTimestamp,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputQuery('');
    setLoading(true);
    setError('');

    try {
      const data = await ragApi.queryKnowledge(queryText.trim(), 5);

      const assistantMessage = {
        id: Date.now() + 1,
        sender: 'assistant',
        text: data.answer,
        sources: data.sources || [],
        retrievalCount: data.retrieval_count || 0,
        hasRelevantContext: data.has_relevant_context,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const detail = err.response?.data?.detail;
      let msg = 'Failed to generate answer from backend.';
      if (typeof detail === 'string') {
        msg = detail;
      } else if (detail && typeof detail === 'object') {
        msg = JSON.stringify(detail);
      } else if (err.message) {
        msg = err.message;
      }
      setError(msg);

      const errorMessage = {
        id: Date.now() + 1,
        sender: 'assistant',
        isError: true,
        text: `Error: ${msg}`,
        sources: [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      {/* Page Header Banner */}
      <div className="glass-panel" style={styles.headerBanner}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          <div style={styles.iconBox}>
            <MessageSquareCode size={24} color="#818cf8" />
          </div>
          <div>
            <h1 style={styles.title}>Personal Coding Mentor</h1>
            <p style={styles.subtitle}>
              Concise mentorship grounded strictly in your personal competitive programming history.
            </p>
          </div>
        </div>

        <div style={styles.statusBadge}>
          <Sparkles size={14} color="#34d399" />
          <span>Personal Mentor Active</span>
        </div>
      </div>

      {/* Main Chat Panel */}
      <div className="glass-panel" style={styles.chatPanel}>
        {/* Messages Container */}
        <div style={styles.messagesContainer}>
          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                ...styles.messageRow,
                justifyContent: msg.sender === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              {msg.sender === 'assistant' && (
                <div style={styles.botAvatar}>
                  <Bot size={18} color="#818cf8" />
                </div>
              )}

              <div
                style={{
                  ...styles.messageBubble,
                  ...(msg.sender === 'user' ? styles.userBubble : styles.assistantBubble),
                  ...(msg.isError ? styles.errorBubble : {}),
                }}
              >
                <div style={styles.messageText}>{msg.text}</div>

                <div style={styles.timestamp}>{msg.timestamp}</div>
              </div>

              {msg.sender === 'user' && (
                <div style={styles.userAvatar}>
                  <UserIcon size={18} color="#fff" />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div style={{ ...styles.messageRow, justifyContent: 'flex-start' }}>
              <div style={styles.botAvatar}>
                <Bot size={18} color="#818cf8" />
              </div>
              <div style={{ ...styles.messageBubble, ...styles.assistantBubble, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <RefreshCw size={16} className="spin" color="#818cf8" />
                <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>Reviewing your personal history & formulating mentor advice...</span>
              </div>
            </div>
          )}
        </div>

        {/* Preset Sample Suggestions */}
        <div style={styles.samplesRow}>
          <span style={{ fontSize: '0.78rem', color: '#9ca3af', fontWeight: '600' }}>Try sample question:</span>
          {SAMPLE_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              disabled={loading}
              onClick={(e) => {
                setInputQuery(q);
                handleSend(e, q);
              }}
              style={styles.sampleChip}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <form onSubmit={(e) => handleSend(e)} style={styles.inputForm}>
          <input
            type="text"
            placeholder="Ask your mentor (e.g. 'How did I approach binary search?' or 'What is my approach to prefix sums?')..."
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            disabled={loading}
            className="input-field"
            style={{ paddingRight: '3.5rem', fontSize: '0.92rem' }}
          />
          <button type="submit" className="btn-primary" disabled={loading || !inputQuery.trim()} style={styles.sendBtn}>
            {loading ? <RefreshCw size={16} className="spin" /> : <Send size={16} />}
          </button>
        </form>
      </div>
    </div>
  );
};

const styles = {
  container: {
    padding: '2rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
    height: 'calc(100vh - 2rem)',
  },
  headerBanner: {
    padding: '1.25rem 2rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '1rem',
    flexWrap: 'wrap',
  },
  iconBox: {
    width: '42px',
    height: '42px',
    borderRadius: '10px',
    background: 'rgba(99, 102, 241, 0.15)',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: '800',
    color: '#f9fafb',
  },
  subtitle: {
    fontSize: '0.85rem',
    color: '#9ca3af',
    marginTop: '0.15rem',
  },
  statusBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    background: 'rgba(16, 185, 129, 0.12)',
    border: '1px solid rgba(16, 185, 129, 0.3)',
    padding: '0.4rem 0.85rem',
    borderRadius: '20px',
    fontSize: '0.8rem',
    color: '#34d399',
    fontWeight: '600',
  },
  chatPanel: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    padding: '1.25rem',
    gap: '1rem',
  },
  messagesContainer: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem',
    paddingRight: '0.5rem',
  },
  messageRow: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.75rem',
  },
  botAvatar: {
    width: '34px',
    height: '34px',
    borderRadius: '50%',
    background: 'rgba(99, 102, 241, 0.15)',
    border: '1px solid rgba(99, 102, 241, 0.3)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  userAvatar: {
    width: '34px',
    height: '34px',
    borderRadius: '50%',
    background: '#4f46e5',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  messageBubble: {
    maxWidth: '75%',
    padding: '0.9rem 1.2rem',
    borderRadius: '14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
    lineHeight: '1.5',
    fontSize: '0.9rem',
  },
  userBubble: {
    background: '#4f46e5',
    color: '#ffffff',
    borderBottomRightRadius: '2px',
  },
  assistantBubble: {
    background: 'rgba(15, 23, 42, 0.85)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    color: '#f1f5f9',
    borderBottomLeftRadius: '2px',
  },
  errorBubble: {
    background: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    color: '#f87171',
  },
  messageText: {
    whiteSpace: 'pre-wrap',
  },
  timestamp: {
    fontSize: '0.7rem',
    color: '#9ca3af',
    alignSelf: 'flex-end',
    marginTop: '0.25rem',
  },
  sourcesBox: {
    marginTop: '0.5rem',
    paddingTop: '0.65rem',
    borderTop: '1px solid rgba(255, 255, 255, 0.1)',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  sourcesHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    fontSize: '0.78rem',
    fontWeight: '700',
    color: '#a5b4fc',
  },
  sourcesGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.4rem',
  },
  sourceChip: {
    background: 'rgba(255, 255, 255, 0.04)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '6px',
    padding: '0.5rem 0.75rem',
    fontSize: '0.78rem',
  },
  sourceTitle: {
    fontWeight: '600',
    color: '#e2e8f0',
  },
  sourceMeta: {
    fontSize: '0.72rem',
    color: '#9ca3af',
    display: 'flex',
    gap: '0.4rem',
    marginTop: '0.15rem',
  },
  noContextBadge: {
    marginTop: '0.4rem',
    padding: '0.35rem 0.65rem',
    borderRadius: '6px',
    background: 'rgba(245, 158, 11, 0.1)',
    border: '1px solid rgba(245, 158, 11, 0.25)',
    color: '#fbbf24',
    fontSize: '0.75rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
  },
  samplesRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    flexWrap: 'wrap',
    paddingTop: '0.5rem',
    borderTop: '1px solid rgba(255, 255, 255, 0.08)',
  },
  sampleChip: {
    background: 'rgba(255, 255, 255, 0.04)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    color: '#a5b4fc',
    fontSize: '0.78rem',
    padding: '0.25rem 0.65rem',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  inputForm: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },
  sendBtn: {
    position: 'absolute',
    right: '0.4rem',
    top: '50%',
    transform: 'translateY(-50%)',
    padding: '0.45rem 0.75rem',
  },
};

export default ChatPage;
