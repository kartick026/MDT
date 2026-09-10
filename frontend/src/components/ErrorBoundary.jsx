import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("MDT Frontend Error Boundary caught error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="card" style={{
          margin: '24px auto',
          maxWidth: '640px',
          background: 'rgba(255, 45, 85, 0.06)',
          border: '1px solid rgba(255, 45, 85, 0.3)',
          borderRadius: '12px',
          padding: '24px',
          textAlign: 'center'
        }}>
          <div style={{ fontSize: '36px', marginBottom: '12px' }}>⚠️</div>
          <h3 style={{ color: '#ff2d55', marginBottom: '8px', fontSize: '18px' }}>
            Something went wrong in this view
          </h3>
          <p style={{ color: '#a0a5b8', fontSize: '14px', marginBottom: '16px' }}>
            {this.state.error?.message || "An unexpected rendering error occurred."}
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}>
            <button
              className="btn btn-secondary"
              onClick={this.handleReset}
              style={{ padding: '8px 16px', fontSize: '13px' }}
            >
              ↺ Try Again
            </button>
            <button
              className="btn btn-primary"
              onClick={() => window.location.reload()}
              style={{ padding: '8px 16px', fontSize: '13px' }}
            >
              Refresh Application
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
