# build + shell example

Exercises hector's `build:` step and the `shell` test type — both run a script
**inside a one-off container** with the project bind-mounted. It also shows that a
config needs **no machine** when its tests are sim-independent (`requires_sim: false`).

```
docker-runner/
├── .hector.yaml        # a build step + two sim-independent shell tests, no machine
└── checks/verify.py    # run inside the python:3.12-slim container
```

What it shows:
- The **build step** (`python:3.12-slim`) writes `generated/values.txt` into the project.
- Two **`shell` tests** (`requires_sim: false`) read that file back — proving build output
  is visible to tests through the shared bind-mount, with no copying.
- No `machines:` block at all, because nothing needs Renode.

## Run

```bash
cd cli/examples/docker-runner
python -m hector test
```

You need Docker available. On first run the `python:3.12-slim` and `alpine:3.19`
images are pulled. Both tests should pass; results land in `results/` with a
`report.html` per test.

To see it fail, change the `printf` in the build step so the values no longer sum to
42 — `checks/verify.py` exits non-zero and the run exits 1.

> Note: the build container may write `generated/` as `root`. Remove it with
> `docker run --rm -v "$PWD:/w" -w /w alpine rm -rf generated` if your host user
> can't.
