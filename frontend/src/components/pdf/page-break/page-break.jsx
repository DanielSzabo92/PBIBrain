import { View } from "@/lib/pdf-primitives";

export const PageBreak = ({
  style
}) => (
  <View style={[{ breakBefore: "page" }, style].filter(Boolean)} />
);
