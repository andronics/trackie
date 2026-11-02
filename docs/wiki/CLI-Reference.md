# CLI Reference

`trackie --help` lists the commands. `trackie <command> --help` shows a command's options.

## Commands

Generated from the code: don't edit, run `uv run scripts/gen-wiki.py`.

<!-- generated:start cli -->
### `trackie config`

Print the effective configuration and where each value came from. Secrets are masked.

| Option | Environment variable | Description |
|---|---|---|
| `--config`, `-c` | `TRACKIE_CONFIG` | Config file (default /etc/trackie/config.yaml; missing is fine). |

### `trackie serve`

Run the HTTP server.

| Option | Environment variable | Description |
|---|---|---|
| `--config`, `-c` | `TRACKIE_CONFIG` | Config file (default /etc/trackie/config.yaml; missing is fine). |

### `trackie version`

Print the version.
<!-- generated:end cli -->

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Failure while running |
| 2 | Bad usage or invalid configuration |

A tracker failing is not an exit code: `serve` keeps running and reports it in `/health`.

### Examples

```sh
trackie serve                                   # what the image runs: uvicorn on listen.host:listen.port
trackie serve -c ./config.yaml                  # with a config file (or TRACKIE_CONFIG)
trackie config                                  # every setting, its value and its source; secrets masked
TRACKIE_IPT_ENABLED=false trackie config        # check a change before restarting
docker exec trackie trackie config              # inside the running container
trackie version
```

`trackie config` prints one line per setting, `key = value  (source)`, where the source is `default`, `file`, or the variable that set it (`TRACKIE_IPT_COOKIE_FILE`).
