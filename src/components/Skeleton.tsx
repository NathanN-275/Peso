import { StyleSheet, View } from 'react-native';
import type { StyleProp, ViewStyle } from 'react-native';

import tokens from '../theme/tokens';

type SkeletonBlockProps = {
  width?: number | `${number}%`;
  height: number;
  radius?: number;
  style?: StyleProp<ViewStyle>;
};

export function SkeletonBlock({
  width = '100%',
  height,
  radius = 8,
  style,
}: SkeletonBlockProps) {
  return (
    <View
      accessibilityLabel="Loading"
      style={[
        styles.block,
        {
          width,
          height,
          borderRadius: radius,
        },
        style,
      ]}
    />
  );
}

export default function SkeletonCard({ height = 96 }: { height?: number }) {
  return <SkeletonBlock height={height} radius={8} />;
}

const styles = StyleSheet.create({
  block: {
    backgroundColor: '#20242D',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.colors.secondaryBorder,
  },
});
