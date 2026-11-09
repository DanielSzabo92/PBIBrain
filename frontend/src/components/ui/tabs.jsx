"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { Tabs as TabsPrimitive } from "radix-ui"

// UI design 6.1 (U-fix-2): each TabsContent element stays in the DOM, so that aria-controls
// of each tab always points to a real element. An inactive panel gets the hidden
// attribute. Its children mount only when the panel is
// active, unless keepMounted is set. A tab row with no panels (a filter row) gives
// "controls" the id of the region that the tabs change.
const TabsContext = React.createContext({ value: undefined, controls: undefined })

function Tabs({
  className,
  orientation = "horizontal",
  value: valueProp,
  defaultValue,
  onValueChange,
  controls,
  ...props
}) {
  const [inner, setInner] = React.useState(defaultValue)
  const controlled = valueProp !== undefined
  const value = controlled ? valueProp : inner
  const change = React.useCallback((next) => {
    if (!controlled) setInner(next)
    onValueChange?.(next)
  }, [controlled, onValueChange])
  const context = React.useMemo(() => ({ value, controls }), [value, controls])
  return (
    <TabsContext.Provider value={context}>
      <TabsPrimitive.Root
        data-slot="tabs"
        data-orientation={orientation}
        orientation={orientation}
        value={value}
        onValueChange={change}
        className={cn("group/tabs flex gap-2 data-[orientation=horizontal]:flex-col", className)}
        {...props} />
    </TabsContext.Provider>
  );
}

function TabsList({
  className,
  variant = "default",
  ...props
}) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn("ui-tabs-list inline-flex w-fit items-center justify-center", className)}
      {...props} />
  );
}

// count: an optional number in a pill. countTone: ok, warn, bad, info, or brand.
function TabsTrigger({
  className,
  count,
  countTone,
  countLabel,
  children,
  ...props
}) {
  const { controls } = React.useContext(TabsContext)
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "ui-tabs-trigger relative inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3.5",
        className
      )}
      {...(controls ? { "aria-controls": controls } : {})}
      {...props}>
      {children}
      {count !== undefined && count !== null ? <span key={count} className="ui-tabs-count" data-tone={countTone || undefined}>{count}{countLabel ? <span className="sr-only"> {countLabel}</span> : null}</span> : null}
    </TabsPrimitive.Trigger>
  );
}

function TabsContent({
  className,
  value,
  keepMounted = false,
  children,
  ...props
}) {
  const { value: active } = React.useContext(TabsContext)
  const selected = active === value
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      forceMount
      value={value}
      className={cn("ui-tabs-content flex-1 outline-none", className)}
      {...props}
      hidden={!selected}>
      {selected || keepMounted ? children : null}
    </TabsPrimitive.Content>
  );
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
