export default function KeywordChips({ matched = [], missing = [] }) {
  return (
    <div className="chips-block">
      <div>
        <h4>Found in your resume</h4>
        <div className="chips">
          {matched.length ? matched.map((k) => <span key={k} className="chip chip-yes">{k}</span>) : <span className="muted">None found</span>}
        </div>
      </div>
      <div>
        <h4>Missing for this role</h4>
        <div className="chips">
          {missing.length ? missing.map((k) => <span key={k} className="chip chip-no">{k}</span>) : <span className="muted">Nothing important missing</span>}
        </div>
      </div>
    </div>
  );
}
