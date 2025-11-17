import { Link, useLocation } from 'react-router-dom';

const navItems = [
  { path: '/', label: 'Overview', icon: '📊' },
  { path: '/trading', label: 'Trading', icon: '💹' },
  { path: '/portfolio', label: 'Portfolio', icon: '💼' },
  { path: '/signals', label: 'Signals', icon: '📡' },
  { path: '/analytics', label: 'Analytics', icon: '📈' },
  { path: '/system', label: 'System', icon: '⚙️' },
  { path: '/logs', label: 'Logs', icon: '📝' },
];

export function Sidebar() {
  const location = useLocation();
  
  return (
    <aside className="w-64 bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-border">
        <h1 className="text-2xl font-bold text-primary">Arthayukti</h1>
        <p className="text-sm text-text-secondary mt-1">HFT Control Panel</p>
      </div>
      
      {/* Navigation */}
      <nav className="flex-1 py-4">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`
                flex items-center gap-3 px-6 py-3 transition-colors
                ${isActive 
                  ? 'bg-primary/10 text-primary border-r-2 border-primary' 
                  : 'text-text-secondary hover:bg-surface-light hover:text-text-primary'
                }
              `}
            >
              <span className="text-xl">{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
