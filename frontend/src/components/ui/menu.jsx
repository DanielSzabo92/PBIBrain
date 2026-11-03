import * as React from "react"
import { Check } from "lucide-react"
import { DropdownMenu as MenuPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

// Menu (UI design 6.1, 9.3), on Radix DropdownMenu.
// groups: [{ label?, items: [{ label, icon?, onSelect?, disabled?, destructive?, checked? }] }].
// A separator goes between groups. Keys: Enter, Space, Down open; arrows; Home, End; typeahead; Escape closes.
function Menu({ trigger, groups = [], align = "start", label, contentClassName, open, onOpenChange }) {
  return (
    <MenuPrimitive.Root modal={false} open={open} onOpenChange={onOpenChange}>
      <MenuPrimitive.Trigger asChild>{trigger}</MenuPrimitive.Trigger>
      <MenuPrimitive.Portal>
        <MenuPrimitive.Content data-slot="menu" className={cn("ui-menu", contentClassName)} align={align} sideOffset={4} aria-label={label}>
          {groups.map((group, groupIndex) => (
            <React.Fragment key={group.label || groupIndex}>
              {groupIndex > 0 ? <MenuPrimitive.Separator className="ui-menu-separator" /> : null}
              <MenuPrimitive.Group aria-label={group.label}>
                {group.label ? <MenuPrimitive.Label className="ui-menu-label" aria-hidden="true">{group.label}</MenuPrimitive.Label> : null}
                {group.items.map((item) => <MenuItem key={item.label} item={item} />)}
              </MenuPrimitive.Group>
            </React.Fragment>
          ))}
        </MenuPrimitive.Content>
      </MenuPrimitive.Portal>
    </MenuPrimitive.Root>
  )
}

function MenuItem({ item }) {
  const Icon = item.icon
  const body = <>{Icon ? <Icon aria-hidden="true" /> : null}<span>{item.label}</span></>
  if (item.checked !== undefined) {
    return (
      <MenuPrimitive.CheckboxItem className="ui-menu-item" checked={item.checked} disabled={item.disabled} onCheckedChange={item.onCheckedChange} onSelect={item.onSelect}>
        <span className="ui-menu-check" aria-hidden="true"><MenuPrimitive.ItemIndicator><Check /></MenuPrimitive.ItemIndicator></span>
        {body}
      </MenuPrimitive.CheckboxItem>
    )
  }
  return (
    <MenuPrimitive.Item className="ui-menu-item" data-destructive={item.destructive || undefined} disabled={item.disabled} onSelect={item.onSelect}>
      {body}
    </MenuPrimitive.Item>
  )
}

export { Menu }
