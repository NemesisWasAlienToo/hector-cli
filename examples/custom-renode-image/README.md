# Building the Renode image in `prepare:`

`renode:` names a Docker image that doesn't exist yet: the first prepare step builds it
from [`docker/Dockerfile`](docker/Dockerfile). Prepare steps run before anything uses
the Renode image, so the sim and the tests get the freshly built one.

```
custom-renode-image/
├── .hector.yaml
└── docker/Dockerfile   # FROM antmicro/renode:1.16.1, plus a marker file
```

```yaml
renode: "hector-example-renode:1.16.1"

prepare:
  - name: Build the Renode image
    script: |                       # no image: → runs on the host, so docker is there
      docker build -q -t hector-example-renode:1.16.1 docker/
```

The shell test reads the marker file (it runs in the `renode:` image when it has no
`image:` of its own), and the robot test boots a machine in the same image.

## Run it

```bash
hector test
```

Tag the image with the Renode version it's based on (`:1.16.1`): hector uses that tag
when a config needs the matching Renode source (Verilator modules, `${RENODE_DIR}`).
