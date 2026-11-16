import {
  usePdfcnTheme,
  useSafeMemo,
} from "@/components/pdf/theme-provider";
import { Text, StyleSheet } from "@/lib/pdf-primitives";
import { resolveColor } from "@/lib/resolve-color";

const createHeadingStyles = (t) => {
  const { heading } = t.typography;
  const { spacing, fontWeights, letterSpacing } = t.primitives;
  const { sectionGap, componentGap, paragraphGap } = t.spacing;
  const base = {
    color: t.colors.foreground,
    fontFamily: heading.fontFamily,
    fontWeight: fontWeights.bold,
    lineHeight: heading.lineHeight,
  };
  return StyleSheet.create({
    capitalize: { textTransform: "capitalize" },
    h1: {
      ...base,
      fontSize: heading.fontSize.h1,
      marginBottom: paragraphGap,
      marginTop: spacing[0],
    },
    h2: {
      ...base,
      fontSize: heading.fontSize.h2,
      marginBottom: paragraphGap,
      marginTop: sectionGap,
    },
    h3: {
      ...base,
      fontSize: heading.fontSize.h3,
      marginBottom: paragraphGap,
      marginTop: componentGap,
    },
    h4: {
      ...base,
      fontSize: heading.fontSize.h4,
      marginBottom: paragraphGap,
      marginTop: paragraphGap,
    },
    h5: {
      ...base,
      fontSize: heading.fontSize.h5,
      marginBottom: spacing[1],
      marginTop: paragraphGap,
    },
    h6: {
      ...base,
      fontSize: heading.fontSize.h6,
      marginBottom: spacing[1],
      marginTop: paragraphGap,
    },
    lowercase: { textTransform: "lowercase" },
    noMargin: { marginBottom: 0, marginTop: 0 },
    trackingNormal: { letterSpacing: letterSpacing.normal },
    trackingTight: { letterSpacing: letterSpacing.tight * 10 },
    trackingTighter: { letterSpacing: letterSpacing.tight * 15 },
    trackingWide: { letterSpacing: letterSpacing.wide * 10 },
    trackingWider: { letterSpacing: letterSpacing.wider * 10 },
    uppercase: {
      letterSpacing: letterSpacing.wider * 10,
      textTransform: "uppercase",
    },
    weightBold: { fontWeight: fontWeights.bold },
    weightMedium: { fontWeight: fontWeights.medium },
    weightNormal: { fontWeight: fontWeights.regular },
    weightSemibold: { fontWeight: fontWeights.semibold },
  });
};

export const Heading = ({
  level = 1,
  align,
  color,
  transform,
  weight,
  tracking,
  noMargin,
  children,
  style
}) => {
  const theme = usePdfcnTheme();
  const styles = useSafeMemo(() => createHeadingStyles(theme), [theme]);
  const safeLevel = Math.min(Math.max(Math.round(level), 1), 6);
  const weightMap = {
    bold: styles.weightBold,
    medium: styles.weightMedium,
    normal: styles.weightNormal,
    semibold: styles.weightSemibold,
  };
  const trackingMap = {
    normal: styles.trackingNormal,
    tight: styles.trackingTight,
    tighter: styles.trackingTighter,
    wide: styles.trackingWide,
    wider: styles.trackingWider,
  };
  const transformMap = {
    capitalize: styles.capitalize,
    lowercase: styles.lowercase,
    uppercase: styles.uppercase,
  };
  const styleArray = [
    styles[`h${safeLevel}`],
  ];
  if (weight && weight in weightMap) {
    styleArray.push(weightMap[weight]);
  }
  if (tracking && tracking in trackingMap) {
    styleArray.push(trackingMap[tracking]);
  }
  if (transform && transform in transformMap) {
    styleArray.push(transformMap[transform]);
  }
  if (noMargin) {
    styleArray.push(styles.noMargin);
  }
  const semantic = {};
  if (align) {
    semantic.textAlign = align;
  }
  if (color) {
    semantic.color = resolveColor(color, theme.colors);
  }
  if (Object.keys(semantic).length > 0) {
    styleArray.push(semantic);
  }
  if (style) {
    styleArray.push(...[style].flat());
  }
  return <Text style={styleArray}>{children}</Text>;
};
