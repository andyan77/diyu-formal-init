import type { JSX } from "react";

export function BrandMark({
  compact = false,
  inverse = false
}: {
  compact?: boolean;
  inverse?: boolean;
}): JSX.Element {
  const source = compact
    ? inverse
      ? "/assets/diyu-symbol-ondark.svg"
      : "/assets/diyu-symbol.svg"
    : inverse
      ? "/assets/diyu-logo-horizontal-ondark.svg"
      : "/assets/diyu-logo-horizontal.svg";
  return <img className={compact ? "brand-symbol" : "brand-wordmark"} src={source} alt="笛语" />;
}
