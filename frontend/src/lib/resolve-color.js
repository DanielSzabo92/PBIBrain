/** Theme color token keys that can be used for the color prop */
export const THEME_COLOR_KEYS = [
  "foreground",
  "background",
  "muted",
  "mutedForeground",
  "primary",
  "primaryForeground",
  "border",
  "accent",
  "destructive",
  "success",
  "warning",
  "info"
];

/** Resolves a color value: theme token key → hex, or raw CSS color as-is. */
export const resolveColor = (value, colors) => {
  const key = value;
  return THEME_COLOR_KEYS.includes(key) ? colors[key] : value;
};
