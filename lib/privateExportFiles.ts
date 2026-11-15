import { requireOptionalNativeModule } from 'expo';
import { File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';

type PrivateExportFiles = {
  purgeOnStartup(): void;
  reserve(): string;
  cancel(id: string): void;
  remove(id: string): void;
  download(id: string, url: string, grant: string): Promise<string>;
};

let startupClean = false;

export function getPrivateExportFiles() {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') {
    throw new Error('Private video export is unavailable on this device.');
  }
  const files = requireOptionalNativeModule<PrivateExportFiles>('PesoPrivateExport');
  if (!files) throw new Error('Update Peso to save private exports on this device.');
  return files;
}

export function ensurePrivateExportStartupCleanup() {
  if (Platform.OS === 'web' || startupClean) return;
  getPrivateExportFiles().purgeOnStartup();
  // Earlier builds put these exact export filenames directly in app cache.
  const legacyExport = /^peso-[a-z0-9]+(?:-[a-z0-9]+)*-(?:clean|pose|barbell|pose-barbell)-[a-f0-9]{8}-[1-9][0-9]*\.mp4$/i;
  for (const entry of Paths.cache.list()) {
    if (entry instanceof File && legacyExport.test(entry.name)) entry.delete();
  }
  startupClean = true;
}
