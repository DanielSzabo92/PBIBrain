// One glyph per object type (docs/design/visual-contract.md §3). The graph, Search, Inspector, Review and
// Merge rows all import from here, so a type looks the same everywhere and is recognisable before its label.
import {
  Activity, Braces, Calculator, ChartColumn, Columns3, Database, FileChartColumn, FolderOpen, Funnel, Layers, Lightbulb,
  Link2, ListFilter, OctagonAlert, PanelsTopLeft, ShieldUser, Sigma, SquareFunction, Table2, Tag, ToggleLeft, Box,
} from "lucide-react";

export const TYPE_ICONS = {
  MODEL: Database,
  TABLE: Table2,
  COLUMN: Columns3,
  MEASURE: Sigma,
  REPORT: FileChartColumn,
  PAGE: PanelsTopLeft,
  VISUAL: ChartColumn,
  RELATIONSHIP: Link2,
  CALCULATION_GROUP: Layers,
  CALCULATION_ITEM: Layers,
  FIELD_PARAMETER: ListFilter,
  SHARED_EXPRESSION: Braces,
  USER_DEFINED_FUNCTION: SquareFunction,
  VISUAL_CALCULATION: Calculator,
  VISUAL_FILTER: Funnel,
  PAGE_FILTER: Funnel,
  REPORT_FILTER: Funnel,
  BUSINESS_CONCEPT: Lightbulb,
  ALIAS: Tag,
  ROLE: ShieldUser,
  BEHAVIOR: Activity,
  SELECTOR: ToggleLeft,
  SELECTOR_OPTION: ToggleLeft,
  CONFLICT: OctagonAlert,
  WORKSPACE: FolderOpen,
  SEMANTIC_ASSERTION: Lightbulb,
};

export function typeIcon(type) {
  return TYPE_ICONS[String(type || "").toUpperCase()] || Box;
}
