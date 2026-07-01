function getButtonVariantColors(variant, colors) {
  if (variant === 'secondary') {
    return {
      backgroundColor: colors.secondarySurface,
      borderColor: colors.secondaryBorder,
      borderWidth: 1,
      textColor: colors.secondaryText,
    };
  }

  return {
    backgroundColor: colors.brand,
    borderColor: 'transparent',
    borderWidth: 0,
    textColor: colors.textPrimary,
  };
}

module.exports = { getButtonVariantColors };
