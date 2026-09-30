import React from "react";
import { LayoutGrid, ListChecks, Search, SlidersHorizontal, SquareMousePointer, Waypoints } from "lucide-react";

const ICONS = {
  overview: LayoutGrid,
  search: Search,
  graph: Waypoints,
  inspector: SquareMousePointer,
  review: ListChecks,
  config: SlidersHorizontal,
};

export default function NavIcon({ name, size = 16 }) {
  const Icon = ICONS[name] || LayoutGrid;
  return <Icon className="nav-icon" size={size} strokeWidth={1.75} aria-hidden="true" />;
}
