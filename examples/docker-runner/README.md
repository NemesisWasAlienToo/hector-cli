# shell example

Exercises hector's `shell` test type, which runs a script **inside a one-off
container** with the project bind-mounted. It also shows that a config needs **no
machine** when it only has `shell` tests (they don't need Renode by default).

```
docker-runner/
├── .hector.yaml        # a prepare step + two sim-independent shell tests, no machine
└── checks/verify.py    # run inside the python:3.12-slim container
```

What it shows:
- A **`prepare:` step** (`python:3.12-slim`) writes `generated/values.txt` into the
  project before any test runs.
- The two **`shell` tests** read that file back — proving the prepare step's output is
  visible to them through the shared bind-mount, with no copying.
- The first test sets **`docker-flags: -e EXPECTED_SUM=42`**: extra `docker run` flags for
  that test's container only. `checks/verify.py` reads the expected sum from it.
- No `machines:` block at all, because nothing needs Renode.

## Run

```bash
cd cli/examples/docker-runner
python -m hector test
```

You need Docker available. On first run the `python:3.12-slim` and `alpine:3.19`
images are pulled. The prepare step and both tests should pass; results land in `results/` with a
`report.html` per test.

To see it fail, change the `printf` in the prepare step so the values no longer sum to
`EXPECTED_SUM` — `checks/verify.py` exits non-zero and the run exits 1.
