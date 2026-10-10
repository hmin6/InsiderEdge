import { useEffect, useId, useState, type HTMLAttributes, type ReactNode } from 'react';
import type { InsiderRole } from '../types/visual';

export type NavigationItem = { label: string; href: string; current?: boolean };

export function AppShell({ children, navigation, utility }: {
  children: ReactNode; navigation: NavigationItem[]; utility?: ReactNode;
}) {
  const mainId = useId();
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      return typeof window !== 'undefined' && window.localStorage.getItem('ie_theme') === 'light' ? 'light' : 'dark';
    } catch { return 'dark'; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { window.localStorage.setItem('ie_theme', theme); } catch { /* Theme remains usable when storage is blocked. */ }
  }, [theme]);
  return <div className="ie-shell">
    <a className="ie-skip-link" href={`#${mainId}`}>Skip to research workspace</a>
    <header className="ie-topbar">
      <a className="ie-brand" href="/" aria-label="InsiderEdge home" aria-current={navigation.some(item => item.href === '/' && item.current) ? 'page' : undefined}><span className="ie-brand-mark" aria-hidden="true">IE</span>InsiderEdge</a>
      <nav className="ie-navigation" aria-label="Primary navigation">
        <button className="ie-theme-toggle" type="button" aria-label="Toggle light/dark theme"
          title="Toggle theme" aria-pressed={theme === 'light'}
          onClick={() => setTheme(current => current === 'dark' ? 'light' : 'dark')}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            {theme === 'dark' ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></>
              : <path d="M20.5 14A9 9 0 0 1 10 3.5 9 9 0 1 0 20.5 14Z" />}
          </svg>
        </button>
        {navigation.filter(item => item.href !== '/').map(item => <a key={item.href} href={item.href} aria-current={item.current ? 'page' : undefined}>{item.label}</a>)}
      </nav>
      {utility && <div className="ie-topbar-utility">{utility}</div>}
    </header>
    <main id={mainId} tabIndex={-1} className="ie-workspace">{children}</main>
    <footer className="ie-footer">Research prioritization · Public SEC evidence · Not personalized investment advice</footer>
  </div>;
}

export function PageContainer({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`ie-page ${className}`} {...props} />;
}

export function ProductHeader({ eyebrow, title, description, actions }: {
  eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode;
}) {
  return <div className="ie-product-header">
    <div>{eyebrow && <p className="ie-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="ie-description">{description}</p>}</div>
    {actions && <div className="ie-header-actions">{actions}</div>}
  </div>;
}

export function SectionHeading({ title, description, actions, id }: {
  title: string; description?: ReactNode; actions?: ReactNode; id?: string;
}) {
  return <div className="ie-section-heading"><div><h2 id={id}>{title}</h2>{description && <p>{description}</p>}</div>{actions && <div className="ie-header-actions">{actions}</div>}</div>;
}

export function Panel({ title, description, actions, children, className = '', ...props }: Omit<HTMLAttributes<HTMLElement>, 'title'> & {
  title: string; description?: ReactNode; actions?: ReactNode;
}) {
  const headingId = useId();
  return <section className={`ie-panel ${className}`} aria-labelledby={headingId} {...props}>
    <SectionHeading id={headingId} title={title} description={description} actions={actions} />
    <div className="ie-panel-body">{children}</div>
  </section>;
}

export type BadgeTone = 'neutral' | 'info' | 'warning' | 'positive' | 'negative';
export function StatusBadge({ children, tone = 'neutral' }: { children: ReactNode; tone?: BadgeTone }) {
  return <span className={`ie-badge ie-badge--${tone}`}>{children}</span>;
}

/** Display the supplied role; role classification remains owned by the data layer. */
export function RoleBadge({ role }: { role: InsiderRole }) {
  return <StatusBadge>{role}</StatusBadge>;
}

export function ScoreStatusBadge({ status, availability }: { status: 'complete' | 'partial' | 'insufficient_data'; availability?: import('../types/api').AvailabilityStatus | null }) {
  if (availability === 'not_scored') return <StatusBadge>Not scored</StatusBadge>;
  const labels = { complete: 'Complete evidence', partial: 'Partial evidence', insufficient_data: 'Insufficient data' };
  return <StatusBadge tone={status === 'complete' ? 'info' : status === 'partial' ? 'warning' : 'neutral'}>{labels[status]}</StatusBadge>;
}

export function Skeleton({ shape = 'line', className = '', ...props }: HTMLAttributes<HTMLSpanElement> & { shape?: 'line' | 'title' | 'block' }) {
  return <span {...props} className={`ie-skeleton ie-skeleton--${shape} ${className}`} aria-hidden="true" />;
}

export function PanelSkeleton({ label = 'Loading research panel', rows = 4 }: { label?: string; rows?: number }) {
  return <div className="ie-panel ie-loading" role="status" aria-label={label}>
    <span className="ie-sr-only">{label}</span>
    <div className="ie-skeleton-content"><Skeleton shape="title" />{Array.from({ length: rows }, (_, index) => <Skeleton key={index} />)}</div>
  </div>;
}

export function StateMessage({ title, children, actions, kind = 'empty' }: {
  title: string; children: ReactNode; actions?: ReactNode; kind?: 'empty' | 'error';
}) {
  return <div className={`ie-state ie-state--${kind}`} role={kind === 'error' ? 'alert' : undefined}>
    <h3>{title}</h3><p>{children}</p>{actions && <div className="ie-header-actions">{actions}</div>}
  </div>;
}
