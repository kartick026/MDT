import { coverageIndicators } from '../utils/coverage';

export default function CoverageIndicators({ result, label = 'Coverage indicators' }) {
  return (
    <section className="coverage-indicators" aria-label={label}>
      {coverageIndicators(result).map(indicator => (
        <div className="coverage-indicator" key={indicator.key}>
          <h4>{indicator.title}</h4>
          <span className="coverage-status">{indicator.label}</span>
          <strong className="coverage-value">{indicator.value}</strong>
          {indicator.notes.map(note => <p key={note}>{note}</p>)}
        </div>
      ))}
    </section>
  );
}
