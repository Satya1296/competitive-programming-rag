import React from 'react';

const StatCard = ({ title, value, subtitle, icon: Icon, color = '#6366f1' }) => {
  return (
    <div className="glass-panel glass-panel-hover" style={styles.card}>
      <div style={styles.header}>
        <span style={styles.title}>{title}</span>
        <div style={{ ...styles.iconContainer, background: `${color}20`, borderColor: `${color}40` }}>
          {Icon && <Icon size={20} color={color} />}
        </div>
      </div>
      <div style={styles.value}>{value}</div>
      {subtitle && <div style={styles.subtitle}>{subtitle}</div>}
    </div>
  );
};

const styles = {
  card: {
    padding: '1.25rem',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '0.75rem',
  },
  title: {
    fontSize: '0.85rem',
    fontWeight: '500',
    color: '#9ca3af',
  },
  iconContainer: {
    width: '36px',
    height: '36px',
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px solid',
  },
  value: {
    fontSize: '1.8rem',
    fontWeight: '700',
    color: '#f9fafb',
    letterSpacing: '-0.02em',
    lineHeight: 1.1,
  },
  subtitle: {
    fontSize: '0.75rem',
    color: '#6b7280',
    marginTop: '0.4rem',
  },
};

export default StatCard;
