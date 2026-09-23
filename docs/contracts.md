# Shared contracts

This file is the interface between independently developed components. The integrator approves changes to
these schemas. Update mocks and consumers in the same integration cycle.

## Job request

```json
{
  "job_id": "demo-001",
  "task": "Describe the requested outcome",
  "input_path": "jobs/demo-001/input",
  "profile": "default"
}
```

## Job status

```json
{
  "job_id": "demo-001",
  "status": "queued",
  "progress": "Waiting to start",
  "started_at": null,
  "finished_at": null,
  "artifacts": [],
  "error": null
}
```

Allowed status values:

```text
queued | running | completed | failed | cancelled
```

## Job result

Replace `payload` with the track-specific output after the task is announced.

```json
{
  "schema_version": "1.0",
  "job_id": "demo-001",
  "summary": "Human-readable result",
  "payload": {},
  "evidence": [],
  "limitations": []
}
```

## Contract change process

1. Record the decision in `coordination/decisions.md`.
2. Update this file.
3. Update mock files.
4. Notify component owners.
5. Update producers and consumers in small reviewable commits.
