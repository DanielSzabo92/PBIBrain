import {
  PageNumber as PageNumberPrimitive,
  TotalPages as TotalPagesPrimitive,
} from "takumi-pdf/primitives";

import {
  usePdfcnTheme,
  useSafeMemo,
} from "@/components/pdf/theme-provider";
import { View, Text as PDFText, StyleSheet, flatten } from "@/lib/pdf-primitives";

const createPageNumberStyles = (t) => {
  const { typography, colors, primitives } = t;
  return StyleSheet.create({
    alignCenter: { textAlign: "center" },
    alignLeft: { textAlign: "left" },
    alignRight: { textAlign: "right" },
    colorForeground: { color: colors.foreground },
    colorMuted: { color: colors.mutedForeground },
    container: {
      display: "flex",
      flexDirection: "row",
      width: "100%",
    },
    justifyCenter: { justifyContent: "center" },
    justifyLeft: { justifyContent: "flex-start" },
    justifyRight: { justifyContent: "flex-end" },
    sizeMd: { fontSize: primitives.typography.base },
    sizeSm: { fontSize: primitives.typography.sm },
    sizeXs: { fontSize: primitives.typography.xs },
    text: { fontFamily: typography.body.fontFamily },
  });
};

export const PageNumber = ({
  format = "Page {page} of {total}",
  align = "center",
  size = "sm",
  muted = true,
  style
}) => {
  const theme = usePdfcnTheme();
  const styles = useSafeMemo(() => createPageNumberStyles(theme), [theme]);
  const alignMap = {
    center: styles.alignCenter,
    left: styles.alignLeft,
    right: styles.alignRight
  };
  const sizeMap = {
    md: styles.sizeMd,
    sm: styles.sizeSm,
    xs: styles.sizeXs
  };
  const justifyMap = {
    center: styles.justifyCenter,
    left: styles.justifyLeft,
    right: styles.justifyRight
  };
  const textStyles = [
    styles.text,
    alignMap[align],
    sizeMap[size],
    muted ? styles.colorMuted : styles.colorForeground,
  ];
  if (style) {
    textStyles.push(...[style].flat());
  }
  return (
    <View style={[styles.container, justifyMap[align]]}>
      {format.split(/({page}|{total})/).map((part, index) => {
        if (part === "{page}") {
          return (
            <PageNumberPrimitive
              key={`page-${index}`}
              style={flatten(textStyles)}
            />
          );
        }
        if (part === "{total}") {
          return (
            <TotalPagesPrimitive
              key={`total-${index}`}
              style={flatten(textStyles)}
            />
          );
        }
        return (
          <PDFText key={`text-${index}`} style={textStyles}>
            {part}
          </PDFText>
        );
      })}
    </View>
  );
};
