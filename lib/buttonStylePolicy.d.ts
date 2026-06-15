type ButtonColors = {
  brand: string;
  textPrimary: string;
  secondarySurface: string;
  secondaryBorder: string;
  secondaryText: string;
};

export function getButtonVariantColors(
  variant: 'primary' | 'secondary',
  colors: ButtonColors
): {
  backgroundColor: string;
  borderColor: string;
  borderWidth: number;
  textColor: string;
};
