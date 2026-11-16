import { isValidElement } from "react";

import { professionalTheme } from "@/lib/pdf-themes/professional";

let serializedTheme = professionalTheme;

const renderForSerializer = (children, theme) => {
  serializedTheme = theme;

  if (!isValidElement(children) || typeof children.type !== "function") {
    return children;
  }

  return (children.type)(children.props);
};

export const PdfcnThemeProvider = ({
  theme,
  children
}) =>
  renderForSerializer(children, theme ?? professionalTheme);

export const usePdfcnTheme = () => serializedTheme;

export const useSafeMemo = (factory, _deps) => factory();
