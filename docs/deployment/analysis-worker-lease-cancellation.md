# Analysis worker lease cancellation

The production worker cancels its active analysis when lease renewal returns
false or raises, or stage persistence returns false or raises. Cancellation is
permanent for that claimed run. The worker does not start a child after an
initial failed stage check, and does not call job completion/failure after it
observes cancellation, including late success, late failure and runner errors.
The existing conditional database RPCs remain authoritative for races between
any final supervisor check and a concurrent revocation.

A shared cancellation event reaches the production process runner. Its watcher
sends termination even while the supervisor is inside a stage-reporting RPC;
if that callback remains blocked, the watcher escalates to kill after two
seconds. Normal cleanup also joins, escalates and joins within bounded periods.
The watcher is stopped and joined on every ordinary runner exit. Existing
analysis deadlines, result/failure classification and process-tree memory
measurements remain in place.

On POSIX the spawned analysis child creates its own session/process group before
loading analysis code. It reports PID/group readiness and waits for supervisor
acknowledgement before any analysis or FFmpeg work. The supervisor checks the
reported PID and actual group against its known child PID. Only that positively
confirmed group may receive group signals; before confirmation, cancellation
signals only the directly owned child. This also terminates ordinary FFmpeg
subprocesses that inherit the analysis group. Detached descendants that create
a new group are outside this contract. The native production target is Linux;
non-POSIX systems use direct-child termination only.

Lease-loss detection is bounded by the existing renewal interval (30–300
seconds), stage reports and configured SDK/network timeouts. This change does
not interrupt an SDK call already executing in the supervisor or heartbeat
thread; child cancellation is independent of such an in-flight stage RPC. A
blocked network operation still has to return at its configured timeout. The
inline analyzer is a synchronous test seam: it checks cancellation around its
callback and cannot preempt arbitrary Python code. Production uses the spawned
process runner.

This is one prerequisite for revocable private media, not a publication fence.
Atomic enqueue/admission rejection, lease-and-tombstone-checked analysis/result
and asset publication, archive creation/completion, rejected late-upload cleanup,
route wiring, provider migrations and real hosted races remain required before
private media activation or launch. Work and Storage uploads already in flight
can complete before cancellation is observed; terminating a process cannot undo
them. No schema, provider, hosted configuration or deployment changes belong to
this slice.
