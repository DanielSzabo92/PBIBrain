import React from "react";
import { GitMerge, House, Inbox, PanelRight, Search, Settings, Waypoints } from "lucide-react";

const ICONS = {
  overview: House,
  search: Search,
  graph: Waypoints,
  inspector: PanelRight,
  review: Inbox,
  devcenter: GitMerge,
  config: Settings,
};

export default function NavIcon({ name, size = 16 }) {
  const Icon = ICONS[name] || House;
  return <Icon className="nav-icon" size={size} strokeWidth={1.75} aria-hidden="true" />;
}
