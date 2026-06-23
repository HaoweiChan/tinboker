import React from 'react';

interface SidebarWrapperProps {
  children: React.ReactNode;
  onClose?: () => void;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
}

export const SidebarWrapper: React.FC<SidebarWrapperProps> = ({
  children,
  onClose,
  title,
  subtitle,
  actions,
  className = '',
}) => {
  return (
    <div
      className={`w-full h-full overflow-y-auto px-6 py-5 ${className}`}
      style={{
        backgroundColor: 'var(--bg-surface)',
      }}
    >
      {/* Header */}
      {(title || onClose || actions) && (
        <div className="flex justify-between items-start mb-6">
          {(title || subtitle) && (
            <div>
              {title && (
                <h1
                  className="text-2xl font-semibold md:text-2xl"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {title}
                </h1>
              )}
              {subtitle && (
                <p
                  className="text-base mt-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {subtitle}
                </p>
              )}
            </div>
          )}

          <div className="flex gap-2 items-center">
            {actions}
            {onClose && (
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg transition-colors hover:bg-muted"
                style={{ color: 'var(--text-secondary)' }}
                aria-label="關閉面板"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>
      )}

      {/* Body */}
      <div className="flex flex-col gap-6 w-full">
        {children}
      </div>
    </div>
  );
};

