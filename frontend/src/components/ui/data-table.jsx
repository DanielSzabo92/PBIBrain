import * as React from "react"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { Checkbox } from "./checkbox"

// DataTable (UI design 6.1): a real table with a hidden caption, a sticky actions column,
// optional row checkboxes, and optional expandable rows. The scroll container is position: relative.
// columns: [{ key, header, render?(row), rowHeader? }]. rows: [{ id, ... }].
// checked: an array of row ids. renderDetail(row): the expanded content. renderActions(row): the actions cell.
function DataTable({ caption, columns = [], rows = [], checked, onCheckedChange, rowLabel = (row) => row.id, renderDetail, renderActions, busy = false, className }) {
  const [open, setOpen] = React.useState(() => new Set())
  const selectable = Array.isArray(checked)
  const toggleOpen = (id) => setOpen((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
  const span = columns.length + (selectable ? 1 : 0) + (renderDetail ? 1 : 0) + (renderActions ? 1 : 0)
  return (
    <div className={cn("ui-table-scroll", className)} aria-busy={busy || undefined}>
      <table className="ui-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {renderDetail ? <th scope="col" className="ui-table-tight"><span className="sr-only">Details</span></th> : null}
            {selectable ? <th scope="col" className="ui-table-tight"><span className="sr-only">Select</span></th> : null}
            {columns.map((column) => <th key={column.key} scope="col">{column.header}</th>)}
            {renderActions ? <th scope="col" className="ui-table-actions" data-ui-actions="">Actions</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isChecked = selectable && checked.includes(row.id)
            const expanded = open.has(row.id)
            const detailId = `detail-${row.id}`
            return (
              <React.Fragment key={row.id}>
                <tr data-checked={isChecked || undefined}>
                  {renderDetail ? (
                    <td className="ui-table-tight">
                      <button type="button" className="ui-table-expand" aria-expanded={expanded} aria-controls={detailId} aria-label={`Details of ${rowLabel(row)}`} onClick={() => toggleOpen(row.id)}>
                        <ChevronRight aria-hidden="true" />
                      </button>
                    </td>
                  ) : null}
                  {selectable ? (
                    <td className="ui-table-tight">
                      <Checkbox size="target" aria-label={`Select ${rowLabel(row)}`} checked={isChecked} onCheckedChange={(value) => onCheckedChange?.(value === true ? [...checked, row.id] : checked.filter((id) => id !== row.id))} />
                    </td>
                  ) : null}
                  {columns.map((column) => {
                    const content = column.render ? column.render(row) : row[column.key]
                    return column.rowHeader ? <th key={column.key} scope="row">{content}</th> : <td key={column.key}>{content}</td>
                  })}
                  {renderActions ? <td className="ui-table-actions" data-ui-actions="">{renderActions(row)}</td> : null}
                </tr>
                {renderDetail ? (
                  <tr id={detailId} className="ui-table-detail" hidden={!expanded}>
                    <td colSpan={span}>{expanded ? renderDetail(row) : null}</td>
                  </tr>
                ) : null}
              </React.Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export { DataTable }
