import React from "react";

// A small directed graph: one model feeding two report artifacts.
export default function BrandMark({ size = 28, className = "" }) {
  return <span className={`brand-mark ${className}`} style={{ width: size, height: size }} aria-hidden="true">
    <svg viewBox="0 0 24 24" width={size * 0.64} height={size * 0.64} fill="none">
      <path d="M7 12h3.5M13.5 12 17 7.5M13.5 12 17 16.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity=".7" />
      <circle cx="5.5" cy="12" r="2.6" fill="currentColor" />
      <circle cx="12" cy="12" r="1.9" fill="currentColor" opacity=".85" />
      <circle cx="18.5" cy="6.5" r="2.1" fill="currentColor" opacity=".75" />
      <circle cx="18.5" cy="17.5" r="2.1" fill="currentColor" opacity=".75" />
    </svg>
  </span>;
}
