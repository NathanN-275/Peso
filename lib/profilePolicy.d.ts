export type ProfileRecord = {
  id: string;
  username: string | null;
  display_name: string | null;
  avatar_path: string | null;
  created_at: string;
  updated_at: string;
  profile_revision: string;
};
export type ProfileDetails = { username?: string | null; display_name?: string | null };
export type NormalizedProfileDetails = { username: string | null; display_name: string | null };
export function isCanonicalUuid(value: unknown): value is string;
export function normalizeProfileDetails(details: ProfileDetails): NormalizedProfileDetails;
export function validateProfileRecord(value: unknown, owner: string): ProfileRecord;
export function validateProfileEnvelope(value: unknown, owner: string): ProfileRecord | null;
export function validateAvatarAttempt(value: unknown, owner: string): { attempt_id: string; avatar_path: string };
export function validatePublishedProfile(value: unknown, owner: string, revision: string | null,
  details: NormalizedProfileDetails, avatarPath?: string | null): ProfileRecord;
