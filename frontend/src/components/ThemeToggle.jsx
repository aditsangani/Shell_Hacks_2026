export default function ThemeToggle({ theme, onToggle }) {
  const nextTheme = theme === 'dark' ? 'light' : 'dark'

  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={onToggle}
      aria-label={`Switch to ${nextTheme} mode`}
      title={`Switch to ${nextTheme} mode`}
    >
      <span className="theme-toggle-icon" aria-hidden="true">
        {theme === 'dark' ? '☀' : '☾'}
      </span>
      <span>{nextTheme === 'light' ? 'Light' : 'Dark'}</span>
    </button>
  )
}
