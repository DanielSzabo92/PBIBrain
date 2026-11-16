import { Children, cloneElement, isValidElement } from "react";

import {
  usePdfcnTheme,
  useSafeMemo,
} from "@/components/pdf/theme-provider";
import {
  View,
  Text as PDFText,
} from "@/lib/pdf-primitives";

import { createTableStyles } from "./table.styles";

export const TableHeader = ({
  children,
  style
}) => (
  <View style={style}>{children}</View>
);

export const TableBody = ({
  children,
  style
}) => (
  <View style={style}>{children}</View>
);

export const TableFooter = ({
  children,
  style
}) => (
  <View style={style}>{children}</View>
);

export const TableCell = ({
  header,
  footer,
  align,
  width,
  children,
  style,
  variant = "line",
  _last
}) => {
  const theme = usePdfcnTheme();
  const styles = useSafeMemo(() => createTableStyles(theme), [theme]);
  const cellStyles =
    width === undefined
      ? [styles.cell]
      : [styles.cellFixed, {
      width
    }];

  const cellVariantStyle = (
    {
      bordered: styles.cellBordered,
      compact: styles.cellCompact,
      minimal: styles.cellMinimal,
      "primary-header": styles.cellPrimaryHeader,
      striped: styles.cellStriped
    }
  )[variant];
  if (cellVariantStyle) {
    cellStyles.push(cellVariantStyle);
  }

  if (variant === "grid" && !_last) {
    cellStyles.push(styles.cellGridBorder);
  } else if (variant === "bordered" && !_last) {
    cellStyles.push(styles.cellBorderedBorder);
  }

  if (align) {
    cellStyles.push({
      textAlign: align
    });
  }

  const styleArray = style ? [...cellStyles, style] : cellStyles;

  let textStyle = styles.cellText;
  if (header) {
    textStyle = {
      bordered: styles.cellTextHeaderBordered,
      compact: styles.cellTextHeaderCompact,
      grid: styles.cellTextHeaderGrid,
      line: styles.cellTextHeaderLine,
      minimal: styles.cellTextHeaderMinimal,
      "primary-header": styles.cellTextHeaderPrimaryHeader,
      striped: styles.cellTextHeaderStriped,
    }[variant];
  } else if (footer) {
    textStyle = styles.cellTextFooter;
  } else if (variant === "compact") {
    textStyle = styles.cellTextCompact;
  }

  const content =
    typeof children === "string" ? (
      <PDFText
        style={[
          textStyle,
          align ? { textAlign: align } : {},
          { margin: 0, padding: 0 },
        ]}
      >
        {children}
      </PDFText>
    ) : (
      children
    );

  return <View style={styleArray}>{content}</View>;
};

export const TableRow = ({
  header,
  footer,
  stripe,
  children,
  style,
  variant = "line"
}) => {
  const theme = usePdfcnTheme();
  const styles = useSafeMemo(() => createTableStyles(theme), [theme]);
  const rowStyles = [
    styles.row,
    {
      bordered: styles.rowBordered,
      compact: styles.rowCompact,
      grid: styles.rowGrid,
      line: styles.rowLine,
      minimal: styles.rowMinimal,
      "primary-header": styles.rowPrimaryHeader,
      striped: styles.rowStriped,
    }[variant],
  ];

  if (header) {
    rowStyles.push(
      {
        bordered: styles.rowHeaderBordered,
        compact: styles.rowHeaderCompact,
        grid: styles.rowHeaderGrid,
        line: styles.rowHeaderLine,
        minimal: styles.rowHeaderMinimal,
        "primary-header": styles.rowHeaderPrimaryHeader,
        striped: styles.rowHeaderStriped,
      }[variant]
    );
  }

  if (footer) {
    if (variant === "striped") {
      rowStyles.push(styles.rowFooterStriped);
    } else {
      rowStyles.push(styles.rowFooter);
    }
  }

  if (stripe && !header && !footer) {
    rowStyles.push(styles.rowStripe);
  }

  const styleArray = style ? [...rowStyles, style] : rowStyles;
  const childArray = Children.toArray(children);
  const processedChildren = childArray.map((child, i) => {
    if (isValidElement(child) && child.type === TableCell) {
      return cloneElement(child, {
        _last: i === childArray.length - 1,
        footer,
        header,
        variant,
      });
    }
    return child;
  });

  return (
    <View
      style={[{ breakInside: "avoid" }, styleArray]
        .flat()
        .filter(Boolean)}
    >
      {processedChildren}
    </View>
  );
};

const processTableChildren = (children, variant, zebraStripe) => {
  let bodyRowIndex = 0;

  return Children.map(children, (child) => {
    if (!isValidElement(child)) {
      return child;
    }

    if (
      child.type === TableHeader ||
      child.type === TableBody ||
      child.type === TableFooter
    ) {
      const isBody = child.type === TableBody;
      const sectionChild = child;
      const sectionChildren = Children.map(
        sectionChild.props.children,
        (rowChild) => {
          if (isValidElement(rowChild) && rowChild.type === TableRow) {
            const rowProps = { variant };

            if (isBody && zebraStripe) {
              const isStripe = bodyRowIndex % 2 === 1;
              bodyRowIndex += 1;
              if (isStripe) {
                rowProps.stripe = true;
              }
            }

            return cloneElement(
              rowChild,
              rowProps
            );
          }
          return rowChild;
        }
      );

      return cloneElement(child, {}, sectionChildren);
    }

    if (child.type === TableRow) {
      return cloneElement(child, { variant });
    }

    return child;
  });
};

export const Table = ({
  children,
  style,
  variant = "line",
  zebraStripe = false,
  noWrap = false
}) => {
  const theme = usePdfcnTheme();
  const styles = useSafeMemo(() => createTableStyles(theme), [theme]);
  const tableStyles = [styles.table];
  const effectiveZebra = variant === "striped" ? true : zebraStripe;

  tableStyles.push(
    {
      bordered: styles.tableBordered,
      compact: styles.tableCompact,
      grid: styles.tableGrid,
      line: styles.tableLine,
      minimal: styles.tableMinimal,
      "primary-header": styles.tablePrimaryHeader,
      striped: styles.tableStriped,
    }[variant]
  );

  const styleArray = style ? [...tableStyles, style] : tableStyles;
  const processedChildren = processTableChildren(
    children,
    variant,
    effectiveZebra
  );

  const inner = <View style={styleArray}>{processedChildren}</View>;
  return noWrap ? (
    <View style={[{ breakInside: "avoid" }].filter(Boolean)}>
      {inner}
    </View>
  ) : (
    inner
  );
};
