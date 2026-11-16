export const StyleSheet = {
  create(styles) {
    return styles;
  },
};

/**
 * pdfcn's shared component tokens follow the PDF convention of using points.
 * Takumi follows browser CSS instead, where numeric lengths are pixels at
 * 96 DPI. Converting at the primitive boundary keeps the public component API
 * and the generated document's physical measurements aligned with Forme.
 */
export const PDF_POINT_TO_CSS_PIXEL = 96 / 72;

export const pointToCssPixel = value => value * PDF_POINT_TO_CSS_PIXEL;

const POINT_LENGTH_PROPERTIES = new Set([
  "blockSize",
  "borderBlockEndWidth",
  "borderBlockStartWidth",
  "borderBlockWidth",
  "borderBottomLeftRadius",
  "borderBottomRightRadius",
  "borderBottomWidth",
  "borderEndEndRadius",
  "borderEndStartRadius",
  "borderInlineEndWidth",
  "borderInlineStartWidth",
  "borderInlineWidth",
  "borderLeftWidth",
  "borderRadius",
  "borderRightWidth",
  "borderStartEndRadius",
  "borderStartStartRadius",
  "borderTopLeftRadius",
  "borderTopRightRadius",
  "borderTopWidth",
  "borderWidth",
  "bottom",
  "columnGap",
  "flexBasis",
  "fontSize",
  "gap",
  "height",
  "inlineSize",
  "inset",
  "insetBlock",
  "insetBlockEnd",
  "insetBlockStart",
  "insetInline",
  "insetInlineEnd",
  "insetInlineStart",
  "left",
  "letterSpacing",
  "margin",
  "marginBlock",
  "marginBlockEnd",
  "marginBlockStart",
  "marginBottom",
  "marginInline",
  "marginInlineEnd",
  "marginInlineStart",
  "marginLeft",
  "marginRight",
  "marginTop",
  "maxBlockSize",
  "maxHeight",
  "maxInlineSize",
  "maxWidth",
  "minBlockSize",
  "minHeight",
  "minInlineSize",
  "minWidth",
  "outlineOffset",
  "outlineWidth",
  "padding",
  "paddingBlock",
  "paddingBlockEnd",
  "paddingBlockStart",
  "paddingBottom",
  "paddingInline",
  "paddingInlineEnd",
  "paddingInlineStart",
  "paddingLeft",
  "paddingRight",
  "paddingTop",
  "right",
  "rowGap",
  "textDecorationThickness",
  "textIndent",
  "top",
  "width",
]);

export const normalizeTakumiStyle = style => {
  const {
    marginHorizontal,
    marginVertical,
    paddingHorizontal,
    paddingVertical,
    ...normalized
  } = style;

  if (marginHorizontal !== undefined) {
    normalized.marginLeft ??= marginHorizontal;
    normalized.marginRight ??= marginHorizontal;
  }
  if (marginVertical !== undefined) {
    normalized.marginBottom ??= marginVertical;
    normalized.marginTop ??= marginVertical;
  }
  if (paddingHorizontal !== undefined) {
    normalized.paddingLeft ??= paddingHorizontal;
    normalized.paddingRight ??= paddingHorizontal;
  }
  if (paddingVertical !== undefined) {
    normalized.paddingBottom ??= paddingVertical;
    normalized.paddingTop ??= paddingVertical;
  }

  const borderSides = ["Top", "Right", "Bottom", "Left"];
  if (normalized.borderWidth !== undefined) {
    normalized.borderStyle ??= "solid";
  }
  for (const side of borderSides) {
    if (normalized[`border${side}Width`] !== undefined) {
      normalized[`border${side}Style`] ??= "solid";
    }
  }

  return Object.fromEntries(
    Object.entries(normalized).map(([property, value]) => [
      property,
      typeof value === "number" && POINT_LENGTH_PROPERTIES.has(property)
        ? pointToCssPixel(value)
        : value,
    ])
  );
};

export const flatten = style => {
  if (!style) {
    return undefined;
  }
  if (Array.isArray(style)) {
    return normalizeTakumiStyle(Object.assign({}, ...style.filter(Boolean)));
  }
  return normalizeTakumiStyle(style);
};

export const View = ({
  children,
  style,
  className,
  ...rest
}) => {
  const {
    wrap,
    fixed,
    break: br,
    minPresenceAhead: _m,
    ...dom
  } = rest;
  const merged = {
    display: "flex",
    flexDirection: "column",
    ...flatten(style),
  };
  if (br) {
    Object.assign(merged, { breakBefore: "page" });
  }
  if (wrap === false) {
    Object.assign(merged, { breakInside: "avoid" });
  }
  if (fixed) {
    Object.assign(merged, { position: "fixed" });
  }
  return (
    <div
      className={className}
      style={merged}
      {...(dom)}
    >
      {children}
    </div>
  );
};

export const Text = ({
  children,
  style,
  className,
  render: _render,
  href,
  src,
  ...rest
}) => {
  const merged = flatten(style);
  const link = href ?? src;
  if (link) {
    return (
      <a href={link} className={className} style={merged} {...(rest)}>
        {children}
      </a>
    );
  }
  return (
    <span className={className} style={merged} {...(rest)}>
      {children}
    </span>
  );
};

export const Image = ({
  src,
  style,
  ...rest
}) => {
  const resolved = typeof src === "string" ? src : src.uri;
  return (
    // eslint-disable-next-line eslint(nextjs/no-img-element) -- PDF primitive, not Next.js page
    <img
      src={resolved}
      style={flatten(style)}
      alt=""
      {...rest}
    />
  );
};

export const Link = ({
  src,
  children,
  style,
  ...rest
}) => (
  <a href={src} style={flatten(style)} {...rest}>
    {children}
  </a>
);

export const Document = ({
  children,
  title,
  style
}) => (
  <div
    data-pdf-document={title}
    style={
      {
        display: "flex",
        flexDirection: "column",
        ...flatten(style)
      }
    }
  >
    {children}
  </div>
);

export const Page = ({
  children,
  size: _size,
  style
}) => (
  <div
    data-pdf-page
    style={
      {
        display: "flex",
        flexDirection: "column",
        ...flatten(style)
      }
    }
  >
    {children}
  </div>
);
