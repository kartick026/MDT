import { useState } from 'react';
import { reviewFinding } from '../api';
import CustomSelect from './CustomSelect';

export default function FindingReview({ analysisId, findingId, review, onSave }) {
  const [classification, setClassification] = useState(review?.classification || 'confirmed');
  const [reason, setReason] = useState(review?.reason || '');
  const [days, setDays] = useState('30');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async event => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onSave(await reviewFinding(analysisId, findingId, { classification, reason, expires_days: Number(days) }));
    } catch (err) {
      setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <details>
      <summary>
        {review ? `Review: ${review.classification.replaceAll('_', ' ')}${review.expired ? ' (expired)' : ''}` : 'Review this finding'}
      </summary>
      {review && <p>{review.reason} · review expires {new Date(review.expires_at * 1000).toLocaleDateString()}</p>}
      <form className="workspace-form" onSubmit={submit}>
        <label>
          Classification
          <CustomSelect
            className="form-select"
            value={classification}
            onChange={e => setClassification(e.target.value)}
          >
            <option value="confirmed">Confirmed</option>
            <option value="false_positive">False positive</option>
            <option value="accepted_risk">Accepted risk</option>
            <option value="unreviewed">Clear review</option>
          </CustomSelect>
        </label>
        <label>
          Reason
          <input
            className="form-input"
            value={reason}
            minLength={3}
            maxLength={2000}
            required
            onChange={e => setReason(e.target.value)}
          />
        </label>
        <label>
          Review again in
          <CustomSelect
            className="form-select"
            value={days}
            onChange={e => setDays(e.target.value)}
          >
            <option value="7">7 days</option>
            <option value="30">30 days</option>
            <option value="90">90 days</option>
          </CustomSelect>
        </label>
        <p>Review labels are saved separately. Findings and calculated scores remain visible and unchanged.</p>
        {error && <p role="alert">{error}</p>}
        <button className="btn btn-ghost" disabled={busy}>
          {busy ? 'Saving…' : 'Save review'}
        </button>
      </form>
    </details>
  );
}
