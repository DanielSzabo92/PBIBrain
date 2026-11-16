import {
  usePdfcnTheme,
  useSafeMemo,
} from "@/components/pdf/theme-provider";
import {
  Text as PDFText,
  StyleSheet,
  View,
} from "@/lib/pdf-primitives";
import { resolveColor } from "@/lib/resolve-color";

const createPageFooterStyles = (t) => {
  const { spacing, fontWeights } = t.primitives;
  const c = t.colors;
  const { body } = t.typography;

  const textBase = {
    color: c.mutedForeground,
    fontFamily: body.fontFamily,
    fontSize: t.primitives.typography.xs,
    lineHeight: body.lineHeight,
  };

  return StyleSheet.create({
    brandedContainer: {
      alignItems: "center",
      backgroundColor: c.primary,
      display: "flex",
      flexDirection: "row",
      justifyContent: "space-between",
      paddingHorizontal: spacing[4],
      paddingVertical: spacing[3],
    },

    centeredContainer: {
      alignItems: "center",
      borderTopColor: c.border,
      borderTopStyle: "solid",
      borderTopWidth: spacing[0.5],
      display: "flex",
      flexDirection: "column",
      paddingTop: spacing[3],
    },

    companyBold: {
      ...textBase,
      color: c.foreground,
      fontWeight: fontWeights.bold,
    },

    companyName: {
      ...textBase,
      color: c.foreground,
      fontWeight: fontWeights.medium,
    },

    contactInfoCenter: {
      ...textBase,
      fontSize: t.primitives.typography.xs - 1,
      marginTop: spacing[0.5],
      textAlign: "center",
    },
    detailedContainer: {
      borderTopColor: c.border,
      borderTopStyle: "solid",
      borderTopWidth: spacing[1],
      display: "flex",
      flexDirection: "column",
      paddingTop: spacing[3],
    },
    detailedLeft: {
      display: "flex",
      flex: 1,
      flexDirection: "column",
    },
    detailedPageNumber: {
      ...textBase,
      borderTopColor: c.border,
      borderTopStyle: "solid",
      borderTopWidth: spacing[0.5],
      paddingTop: spacing[2],
      textAlign: "center",
    },
    detailedRight: {
      alignItems: "flex-end",
      display: "flex",
      flexDirection: "column",
    },
    detailedTopRow: {
      alignItems: "flex-start",
      display: "flex",
      flexDirection: "row",
      justifyContent: "space-between",
      marginBottom: spacing[2],
    },

    minimalContainer: {
      alignItems: "center",
      display: "flex",
      flexDirection: "row",
      justifyContent: "space-between",
      paddingBottom: spacing[1],
      paddingTop: spacing[1],
    },
    simpleContainer: {
      alignItems: "center",
      borderTopColor: c.border,
      borderTopStyle: "solid",
      borderTopWidth: spacing[0.5],
      display: "flex",
      flexDirection: "row",
      justifyContent: "space-between",
      paddingTop: spacing[3],
    },
    textBranded: {
      ...textBase,
      color: c.primaryForeground,
      fontWeight: fontWeights.medium,
    },
    textBrandedRight: {
      ...textBase,
      color: c.primaryForeground,
      textAlign: "right",
    },
    textCenter: {
      ...textBase,
      flex: 1,
      textAlign: "center",
    },
    textCenteredVariant: {
      ...textBase,
      marginBottom: spacing[1],
      textAlign: "center",
    },

    textLeft: {
      ...textBase,
      flex: 1,
    },
    textRight: {
      ...textBase,
      textAlign: "right",
    },
    threeColumnCenter: {
      alignItems: "center",
      display: "flex",
      flex: 1,
      flexDirection: "column",
    },
    threeColumnContainer: {
      alignItems: "flex-start",
      borderTopColor: c.border,
      borderTopStyle: "solid",
      borderTopWidth: spacing[0.5],
      display: "flex",
      flexDirection: "row",
      justifyContent: "space-between",
      paddingTop: spacing[3],
    },
    threeColumnLeft: {
      display: "flex",
      flex: 1,
      flexDirection: "column",
    },
    threeColumnRight: {
      alignItems: "flex-end",
      display: "flex",
      flex: 1,
      flexDirection: "column",
    },
  });
};

const applyTextColor = (styles, color) => {
  if (!color) {
    return styles;
  }
  return [...styles, { color }];
};

const renderBranded = (
  styles,
  containerStyles,
  leftStyle,
  rightStyle,
  leftText,
  rightText,
  noWrap
) => (
  <View wrap={!noWrap} style={containerStyles}>
    {leftText && <PDFText style={leftStyle}>{leftText}</PDFText>}
    {rightText && <PDFText style={rightStyle}>{rightText}</PDFText>}
  </View>
);

const renderCentered = (
  styles,
  containerStyles,
  textStyle,
  leftText,
  rightText,
  noWrap
) => (
  <View wrap={!noWrap} style={containerStyles}>
    {leftText && <PDFText style={textStyle}>{leftText}</PDFText>}
    {rightText && <PDFText style={textStyle}>{rightText}</PDFText>}
  </View>
);

const renderThreeColumn = (
  styles,
  containerStyles,
  leftStyle,
  centerStyle,
  rightStyle,
  leftText,
  rightText,
  address,
  phone,
  email,
  website,
  noWrap
) => (
  <View wrap={!noWrap} style={containerStyles}>
    <View style={styles.threeColumnLeft}>
      {leftText && <PDFText style={leftStyle}>{leftText}</PDFText>}
      {address && <PDFText style={styles.textLeft}>{address}</PDFText>}
    </View>
    <View style={styles.threeColumnCenter}>
      {phone && <PDFText style={centerStyle}>{phone}</PDFText>}
      {email && <PDFText style={centerStyle}>{email}</PDFText>}
      {website && <PDFText style={centerStyle}>{website}</PDFText>}
    </View>
    <View style={styles.threeColumnRight}>
      {rightText && <PDFText style={rightStyle}>{rightText}</PDFText>}
    </View>
  </View>
);

const renderDetailed = (
  styles,
  containerStyles,
  companyStyle,
  addrStyle,
  contactStyle,
  pageNumStyle,
  leftText,
  rightText,
  address,
  phone,
  email,
  website,
  noWrap
) => (
  <View wrap={!noWrap} style={containerStyles}>
    <View style={styles.detailedTopRow}>
      <View style={styles.detailedLeft}>
        {leftText && <PDFText style={companyStyle}>{leftText}</PDFText>}
        {address && <PDFText style={addrStyle}>{address}</PDFText>}
      </View>
      <View style={styles.detailedRight}>
        {phone && <PDFText style={contactStyle}>{`Phone: ${phone}`}</PDFText>}
        {email && <PDFText style={contactStyle}>{`Email: ${email}`}</PDFText>}
        {website && <PDFText style={contactStyle}>{`Web: ${website}`}</PDFText>}
      </View>
    </View>
    {rightText && <PDFText style={pageNumStyle}>{rightText}</PDFText>}
  </View>
);

const renderMinimal = (
  styles,
  containerStyles,
  leftStyle,
  rightStyle,
  leftText,
  rightText,
  noWrap
) => (
  <View wrap={!noWrap} style={containerStyles}>
    {leftText && <PDFText style={leftStyle}>{leftText}</PDFText>}
    {rightText && <PDFText style={rightStyle}>{rightText}</PDFText>}
  </View>
);

const renderSimple = (
  styles,
  containerStyles,
  leftStyle,
  centerStyle,
  rightStyle,
  leftText,
  centerText,
  rightText,
  noWrap
) => (
  <View wrap={!noWrap} style={containerStyles}>
    {leftText && <PDFText style={leftStyle}>{leftText}</PDFText>}
    {centerText && <PDFText style={centerStyle}>{centerText}</PDFText>}
    {rightText && <PDFText style={rightStyle}>{rightText}</PDFText>}
  </View>
);

export const PageFooter = ({
  leftText,
  rightText,
  centerText,
  variant = "simple",
  background,
  textColor,
  marginTop,
  address,
  phone,
  email,
  website,
  fixed = false,
  sticky = false,
  pagePadding = 0,
  noWrap = true,
  style
}) => {
  const theme = usePdfcnTheme();
  const styles = useSafeMemo(() => createPageFooterStyles(theme), [theme]);
  const _isFixed = fixed || sticky;
  const mt = sticky ? 0 : (marginTop ?? theme.spacing.sectionGap);
  const resolvedTextColor = textColor
    ? resolveColor(textColor, theme.colors)
    : undefined;
  // A footer passed as a render option lays out at full page width, so the
  // page padding has to come from the footer itself to line up with the content.
  const placement = sticky
    ? {
        bottom: pagePadding,
        left: pagePadding,
        position: "absolute",
        right: pagePadding,
      }
    : { paddingLeft: pagePadding, paddingRight: pagePadding };

  const applyOverrides = base => {
    if (background) {
      base.push({ backgroundColor: resolveColor(background, theme.colors) });
    }
    if (style) {
      base.push(style);
    }
    base.push(placement);
    return base;
  };

  const variantRenderers = {
    branded: () =>
      renderBranded(
        styles,
        applyOverrides([styles.brandedContainer, { marginTop: mt }]),
        applyTextColor([styles.textBranded], resolvedTextColor),
        applyTextColor([styles.textBrandedRight], resolvedTextColor),
        leftText,
        rightText,
        noWrap
      ),
    centered: () =>
      renderCentered(
        styles,
        applyOverrides([styles.centeredContainer, { marginTop: mt }]),
        applyTextColor([styles.textCenteredVariant], resolvedTextColor),
        leftText,
        rightText,
        noWrap
      ),
    detailed: () =>
      renderDetailed(
        styles,
        applyOverrides([styles.detailedContainer, { marginTop: mt }]),
        applyTextColor([styles.companyBold], resolvedTextColor),
        applyTextColor([styles.textLeft], resolvedTextColor),
        applyTextColor([styles.textRight], resolvedTextColor),
        applyTextColor([styles.detailedPageNumber], resolvedTextColor),
        leftText,
        rightText,
        address,
        phone,
        email,
        website,
        noWrap
      ),
    minimal: () =>
      renderMinimal(
        styles,
        applyOverrides([styles.minimalContainer, { marginTop: mt }]),
        applyTextColor([styles.textLeft], resolvedTextColor),
        applyTextColor([styles.textRight], resolvedTextColor),
        leftText,
        rightText,
        noWrap
      ),
    simple: () =>
      renderSimple(
        styles,
        applyOverrides([styles.simpleContainer, { marginTop: mt }]),
        applyTextColor([styles.textLeft], resolvedTextColor),
        applyTextColor([styles.textCenter], resolvedTextColor),
        applyTextColor([styles.textRight], resolvedTextColor),
        leftText,
        centerText,
        rightText,
        noWrap
      ),
    "three-column": () =>
      renderThreeColumn(
        styles,
        applyOverrides([styles.threeColumnContainer, { marginTop: mt }]),
        applyTextColor([styles.companyName], resolvedTextColor),
        applyTextColor([styles.contactInfoCenter], resolvedTextColor),
        applyTextColor([styles.textRight], resolvedTextColor),
        leftText,
        rightText,
        address,
        phone,
        email,
        website,
        noWrap
      ),
  };

  return variantRenderers[variant]();
};
