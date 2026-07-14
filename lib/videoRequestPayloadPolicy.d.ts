import type {
  AnalyzedVideoExportOptions,
  RegisterUploadedVideoRequest,
} from './backendApi';

export function buildRegisterUploadedVideoPayload(
  input: RegisterUploadedVideoRequest
): RegisterUploadedVideoRequest;

export function buildAnalyzedVideoExportPayload(
  input?: Partial<AnalyzedVideoExportOptions>
): AnalyzedVideoExportOptions;
