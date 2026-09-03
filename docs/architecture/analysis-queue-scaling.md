# Analysis queue scaling follow-up

## Current boundary

PostgreSQL `analysis_jobs` remains the source of truth for web and mobile. The
current beta has one continuously running worker, durable leases and
heartbeats, bounded retries, and a three-active-job limit per user.

## Scale trigger

Add horizontal worker scaling when representative beta traffic shows that the
oldest queued job exceeds the accepted wait-time target. Scale from queue depth
and oldest-job age rather than API CPU.

## Target design

- Publish committed jobs to a managed queue through a transactional outbox.
- Run multiple competing worker containers while keeping job effects
  idempotent by job ID and attempt generation.
- Admit work fairly across users while preserving each user's three-active-job
  limit and a separate global analysis-concurrency cap.
- Renew leases for long jobs, retry transient failures with bounded exponential
  backoff and jitter, and isolate exhausted or permanent failures from the live
  queue.
- Monitor queue depth, oldest-job age, attempt count, processing latency,
  failure class, and isolated-job count; alert on the wait-time and failure-rate
  objectives chosen before rollout.

## Rollout gates

Do not replace the current queue until staging proves that duplicate delivery
cannot duplicate analysis results or assets, user fairness holds under burst
load, worker termination recovers cleanly, and scaling never exceeds the
configured downstream compute/storage budget.

## Primary references

- [Amazon SQS visibility timeouts and redelivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon ECS queue-backed autoscaling guidance](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-autoscaling-best-practice.html)
- [Google Cloud Tasks concurrency, rate, and retry controls](https://docs.cloud.google.com/tasks/docs/configuring-queues)
