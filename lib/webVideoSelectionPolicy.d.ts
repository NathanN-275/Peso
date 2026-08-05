export type ObjectUrlLease = {
  url: string;
  revoke: () => void;
};

export type WebVideoPreview = {
  thumbnail: string;
  durationSeconds: number;
};

export function createObjectUrlLease(
  file: Blob,
  urlApi?: Pick<typeof URL, 'createObjectURL' | 'revokeObjectURL'>
): ObjectUrlLease;

export function createWebVideoPreview(
  uri: string,
  options: { timeMs: number; quality?: number },
  documentRef?: Document
): Promise<WebVideoPreview>;
