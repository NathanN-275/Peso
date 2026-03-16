const tokens = require('./src/theme/tokens.cjs');

module.exports = {
  content: [
    './App.{js,jsx,ts,tsx}',
    './src/**/*.{js,jsx,ts,tsx}',
    './screens/**/*.{js,jsx,ts,tsx}',
    './context/**/*.{js,jsx,ts,tsx}',
  ],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        bg: tokens.colors.bg,
        brand: tokens.colors.brand,
        'brand-press': tokens.colors.brandPress,
        'text-primary': tokens.colors.textPrimary,
        'text-muted': tokens.colors.textMuted,
        'input-bg': tokens.colors.inputBg,
        'input-border': tokens.colors.inputBorder,
      },
      borderRadius: {
        button: tokens.radii.button,
        input: tokens.radii.input,
      },
      spacing: {
        'screen-x': tokens.spacing.screenX,
        'logo-top': tokens.spacing.logoTop,
        'logo-bottom': tokens.spacing.logoBottom,
        'button-gap': tokens.spacing.buttonGap,
      },
      fontSize: {
        button: [tokens.typography.buttonSize, { lineHeight: tokens.typography.buttonLineHeight }],
        label: [tokens.typography.labelSize, { lineHeight: tokens.typography.labelLineHeight }],
      },
      letterSpacing: {
        button: tokens.typography.buttonLetterSpacing,
      },
    },
  },
  plugins: [],
};
