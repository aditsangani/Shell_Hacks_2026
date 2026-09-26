const SECTIONS = [
  { id: 'unusualness', number: '1', label: 'Unusualness' },
  { id: 'market-context', number: '2', label: 'Market context' },
  { id: 'evidence', number: '3', label: 'Evidence' },
  { id: 'history', number: '4', label: 'History' },
  { id: 'conclusion', number: '5', label: 'Conclusion' },
]

export { SECTIONS }

export default function SectionNav({ active, onSelect }) {
  return (
    <nav className="section-nav" aria-label="Investigation sections">
      {SECTIONS.map((section) => (
        <button
          key={section.id}
          type="button"
          className={active === section.id ? 'section-nav-item on' : 'section-nav-item'}
          onClick={() => onSelect(section.id)}
          aria-current={active === section.id ? 'step' : undefined}
        >
          <span>{section.number}</span>
          {section.label}
        </button>
      ))}
    </nav>
  )
}
