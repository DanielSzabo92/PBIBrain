import { View } from "@/lib/pdf-primitives";

export const KeepTogether = ({
  children,
  style
}) => (
  <View style={[{ breakInside: "avoid" }, style].filter(Boolean)}>
    {children}
  </View>
);
