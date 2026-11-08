// ImpactItemRow (UI design 4.5): a two-line row of the Impact table.
// Line 1: status chip, type, name button, place, severity, tags. Line 2: reason phrase, shortest path, "<n> other paths".
// One primary button; the other allowed actions are in the row menu.
import React from "react";
import { MoreHorizontal, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Menu } from "@/components/ui/menu";
import { StatusBadge } from "@/components/ui/status-badge";
import { t } from "../copy.js";
import { formatDaxName, formatObjectRef } from "../phrases.js";
import {
  STATUS_TONE,
  actionLabel,
  itemStatus,
  menuActions,
  otherPathsText,
  primaryAction,
  severityLabel,
  shortestPathText,
  statusLabel,
} from "../screens/impact/impactModel.js";

export const IMPACT_ROW_HEIGHT = 64;

export default function ImpactItemRow({
  item,
  rowIndex,
  place,
  proposed,
  checked,
  active,
  disabled,
  reasonId,
  pendingAction,
  onCheck,
  onOpen,
  onAction,
}) {
  const status = itemStatus(item);
  const primary = primaryAction(item);
  const others = menuActions(item);
  const obj = item.impacted_object;
  const name = obj?.table && obj?.name && obj?.object_type !== "table"
    ? formatDaxName(obj.table, obj.name)
    : formatObjectRef(obj?.name ?? item.id);
  const other = otherPathsText(item.other_paths_count ?? 0);
  return (
    <tr
      className="dc-impact-row"
      data-item-id={item.id}
      data-status={status}
      aria-rowindex={rowIndex + 2}
      aria-selected={active || undefined}
      data-active={active || undefined}
      data-checked={checked || undefined}
      style={{ height: IMPACT_ROW_HEIGHT }}>
      <td className="dc-impact-cell-check">
        <Checkbox size="target" checked={checked} aria-label={t("impact.row.select", { name })} onCheckedChange={(value) => onCheck(item, value === true)} />
      </td>
      <th scope="row" className="dc-impact-cell-item">
        <div className="dc-impact-line1">
          <StatusBadge tone={STATUS_TONE[status]} label={statusLabel(status)} />
          <span className="dc-impact-type">{item.impacted_object?.object_type}</span>
          <button type="button" className="dc-impact-name" onClick={(event) => onOpen(item, event.currentTarget)}>{name}</button>
          {item.certainty === "possible" ? <span className="dc-impact-tag">{t("impact.tag.possible")}</span> : null}
          {item.severity === "not_changed_by_this_plan" ? <span className="dc-impact-tag">{t("impact.tag.not_changed")}</span> : null}
          {proposed ? (
            <span className="dc-impact-tag" data-tag="proposed">
              <Terminal aria-hidden="true" />
              {t("impact.tag.proposed")}
            </span>
          ) : null}
        </div>
        <div className="dc-impact-line2">
          <span className="dc-impact-reason">{item.reason_text}</span>
          {item.path?.length ? <span className="dc-impact-path">{shortestPathText(item)}</span> : null}
          {other ? <span className="dc-impact-other">{other}</span> : null}
        </div>
      </th>
      <td className="dc-impact-cell-place">{place}</td>
      <td className="dc-impact-cell-severity">{severityLabel(item.severity)}</td>
      <td className="dc-impact-cell-action">
        <div className="dc-impact-actions" data-ui-actions="">
          {primary ? (
            <Button
              variant="outline"
              size="sm"
              disabled={disabled}
              aria-describedby={disabled ? reasonId : undefined}
              loading={pendingAction === primary}
              loadingText={t("shared.updating")}
              onClick={(event) => onAction(item, primary, event.currentTarget)}>
              {actionLabel(primary)}
            </Button>
          ) : null}
          <Menu
            align="end"
            label={t("impact.row.more", { name })}
            trigger={
              <Button variant="ghost" size="icon-sm" aria-label={t("impact.row.more", { name })}>
                <MoreHorizontal />
              </Button>
            }
            groups={[
              {
                items: [
                  { label: t("impact.row.open"), onSelect: () => onOpen(item, null) },
                  ...others.map((action) => ({ label: actionLabel(action), disabled, onSelect: () => onAction(item, action, null) })),
                ],
              },
            ]}
          />
        </div>
      </td>
    </tr>
  );
}
