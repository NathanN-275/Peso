const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const NIL_UUID = '00000000-0000-0000-0000-000000000000';
const INVALID_RESPONSE = 'The profile response was invalid. Reload your profile and try again.';

function isCanonicalUuid(value) {
  return typeof value === 'string' && UUID.test(value) && value !== NIL_UUID;
}

function exactKeys(value, keys) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

function normalizeProfileDetails(details) {
  const text = (value) => {
    if (value !== null && value !== undefined && typeof value !== 'string') throw new Error('Invalid profile details.');
    return value?.trim() || null;
  };
  const username = text(details.username)?.toLowerCase() ?? null;
  const display_name = text(details.display_name);
  if (username !== null && !/^[a-z0-9_]{3,30}$/.test(username)) {
    throw new Error('Username must be 3-30 letters, numbers, or underscores.');
  }
  if (display_name !== null && Array.from(display_name).length > 80) {
    throw new Error('Display name must be 80 characters or less.');
  }
  return { username, display_name };
}

function validOwnedAvatarPath(path, owner) {
  // Existing timestamp avatar keys remain readable until the separate signed-reader migration.
  return path === null || (typeof path === 'string'
    && path.startsWith(owner + '/') && /^avatar-[A-Za-z0-9-]+\.(?:jpg|jpeg|png|webp)$/.test(path.slice(owner.length + 1)));
}

function validateProfileRecord(value, owner) {
  const fields = ['id', 'username', 'display_name', 'avatar_path', 'created_at', 'updated_at', 'profile_revision'];
  const timestamp = (time) => typeof time === 'string'
    && /^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(time) && Number.isFinite(Date.parse(time));
  if (!isCanonicalUuid(owner) || !exactKeys(value, fields) || value.id !== owner
      || !isCanonicalUuid(value.profile_revision)
      || !(value.username === null || (typeof value.username === 'string' && /^[A-Za-z0-9_]{3,30}$/.test(value.username)))
      || !(value.display_name === null || (typeof value.display_name === 'string' && Array.from(value.display_name).length <= 80))
      || !validOwnedAvatarPath(value.avatar_path, owner) || !timestamp(value.created_at) || !timestamp(value.updated_at)) {
    throw new Error(INVALID_RESPONSE);
  }
  return value;
}

function validateProfileEnvelope(value, owner) {
  if (!exactKeys(value, ['profile'])) throw new Error(INVALID_RESPONSE);
  return value.profile === null ? null : validateProfileRecord(value.profile, owner);
}

function validateAvatarAttempt(value, owner) {
  if (!isCanonicalUuid(owner) || !exactKeys(value, ['attempt_id', 'avatar_path'])
      || !isCanonicalUuid(value.attempt_id) || value.avatar_path !== `${owner}/avatar-${value.attempt_id}.jpg`) {
    throw new Error(INVALID_RESPONSE);
  }
  return value;
}

function validatePublishedProfile(value, owner, revision, details, avatarPath) {
  const profile = validateProfileRecord(value, owner);
  if (profile.profile_revision === revision || profile.username !== details.username
      || profile.display_name !== details.display_name || (avatarPath !== undefined && profile.avatar_path !== avatarPath)) {
    throw new Error(INVALID_RESPONSE);
  }
  return profile;
}

module.exports = { isCanonicalUuid, normalizeProfileDetails, validateProfileEnvelope,
  validateProfileRecord, validateAvatarAttempt, validatePublishedProfile };
