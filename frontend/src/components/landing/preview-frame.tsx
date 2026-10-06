import type { ReactNode } from "react";

export function PreviewFrame({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div aria-hidden="true" className={`landing-preview ${className}`}>
      <div className="landing-preview-bar">
        <span />
        <span />
        <span />
        <div>{title}</div>
      </div>
      {children}
    </div>
  );
}
