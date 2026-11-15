# Peso private media

Private-media language distinguishes permission to start work, an observed
upload response, and evidence that cleanup can finish.

## Language

**Source write attempt**:
One permitted dispatch of an original lift upload for an owner's reservation.
_Avoid_: Upload success, cleanup receipt

**Upload success observation**:
A record that the storage API returned success for a particular write attempt.
It does not establish that all effects of that attempt have settled or been removed.
_Avoid_: Settlement, erasure certificate

**Cleanup settlement**:
Evidence that a write can produce no further effects and that its retained
effects have received the required cleanup disposition.
_Avoid_: Expiry, cancellation, object-not-found

**Generated media write attempt**:
One permitted dispatch of a derived lift asset or frozen Saved Lift package,
tied to its input lifts and the work that produced it.
_Avoid_: Published asset, cleanup receipt

**Analysis snapshot**:
The particular model and analysis contents used to render a lift export.
An analysis identity can remain the same while its snapshot changes.
_Avoid_: Analysis ID, latest export

**Archive snapshot**:
The frozen selection of lift files and analysis snapshots included in a published
Saved Lift ZIP. Later analysis changes do not change that package; access still
depends on the owner, selected lifts and expiry.
_Avoid_: Latest analysis archive, mutable export bundle

**Avatar write attempt**:
One permitted dispatch of a normalized profile image for an owner's live session
and expected profile revision. The retained attempt is independent of lift media.
_Avoid_: Current avatar, cleanup receipt

**Profile revision**:
A random nonce rotated on every profile insert or update. It binds a metadata
save or avatar publication to the exact profile state read by that caller.
_Avoid_: Timestamp, username, session ID
