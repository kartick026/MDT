import { useState, createContext, useContext } from 'react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = (message, type = 'info', duration = 4000) => {
    const id = Date.now() + Math.random().toString(36).substring(2, 6);
    setToasts(prev => [...prev, { id, message, type }]);

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }
  };

  const removeToast = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      <div className="toast-container" style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        maxWidth: '380px',
        pointerEvents: 'none'
      }}>
        {toasts.map(toast => {
          const typeStyles = {
            success: { bg: 'rgba(0, 255, 136, 0.15)', border: '#00ff88', icon: '✓', color: '#00ff88' },
            error:   { bg: 'rgba(255, 45, 85, 0.15)', border: '#ff2d55', icon: '✕', color: '#ff2d55' },
            warning: { bg: 'rgba(251, 191, 36, 0.15)', border: '#fbbf24', icon: '⚠', color: '#fbbf24' },
            info:    { bg: 'rgba(0, 212, 255, 0.15)', border: '#00d4ff', icon: 'ℹ', color: '#00d4ff' },
          }[toast.type] || { bg: 'rgba(255,255,255,0.1)', border: '#888', icon: '●', color: '#fff' };

          return (
            <div
              key={toast.id}
              className="toast-item"
              style={{
                pointerEvents: 'auto',
                background: '#0d1020',
                border: `1px solid ${typeStyles.border}`,
                boxShadow: `0 8px 24px rgba(0,0,0,0.5), 0 0 12px ${typeStyles.bg}`,
                borderRadius: '8px',
                padding: '12px 16px',
                color: '#fff',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                animation: 'toastSlideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)'
              }}
            >
              <span style={{ color: typeStyles.color, fontWeight: 'bold', fontSize: '15px' }}>
                {typeStyles.icon}
              </span>
              <span style={{ flex: 1, lineHeight: 1.4 }}>{toast.message}</span>
              <button
                onClick={() => removeToast(toast.id)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#6c7293',
                  cursor: 'pointer',
                  padding: '2px 4px',
                  fontSize: '14px',
                  lineHeight: 1
                }}
              >
                ✕
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return {
      addToast: (msg, type) => console.log(`[Toast ${type}]: ${msg}`),
      removeToast: () => {}
    };
  }
  return ctx;
}
