import React from "react";

export default function NavIcon({ name }) {
  const paths = {
    overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    search: "M21 21l-5-5 M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0",
    graph: "M3 9h6v6H3z M15 3h6v6h-6z M15 15h6v6h-6z M9 12h3V6h3 M12 12v6h3",
    inspector: "M5 3h14v18H5z M9 7h6 M9 11h6 M9 15h3",
    review: "M9 6h12 M9 12h12 M9 18h12 M2 6l2 2 3-4 M2 12l2 2 3-4 M2 18l2 2 3-4",
    config: "M3 6h18 M3 12h18 M3 18h18 M8 3v6 M16 9v6 M8 15v6",
  };
  return <svg className="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
