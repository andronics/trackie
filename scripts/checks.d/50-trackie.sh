#!/bin/sh
# trackie's own checks (project-owned): no tracker user ID in a tracked file. Base's
# personal-data guard (base-ci.yml) covers public IPs and the denylist. Quiet on a pass.
set -eu
cd "$(dirname "$0")/../.."

python3 scripts/check-tracker-user-ids.py
echo "50-trackie OK"
