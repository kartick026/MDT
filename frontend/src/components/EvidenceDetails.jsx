import { useState } from 'react';

export default function EvidenceDetails({ label, value }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>{label}</summary>{open && <pre>{JSON.stringify(value,null,2)}</pre>}</details>;
}
