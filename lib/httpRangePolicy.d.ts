export type ByteRange = {
  start: number;
  end: number;
};

export function resolveByteRange(rangeHeader: string | undefined, size: number): ByteRange | null;
