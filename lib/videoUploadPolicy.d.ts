export function normalizeVideoUploadFileName(filename: string, contentType: string): string;
export function getStorageUploadErrorMessage(detail: string): string;
export function buildReservedUploadRequest(
  fileBody: Blob | File,
  contract: {
    upload_method: 'PUT';
    upload_body_format: 'raw';
    upload_authentication: 'none' | 'bearer';
    upload_headers: Record<string, string>;
  },
  accessToken: string,
): {
  method: 'PUT';
  headers: Record<string, string>;
  body: Blob | File;
};
export function resolveReservedUploadUrl(
  uploadUrl: string,
  backendUrl: string,
  uploadAuthentication: 'none' | 'bearer',
): string;
