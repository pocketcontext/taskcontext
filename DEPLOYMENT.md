# First release deployment

Deployed on 23 September 2026 at **https://tasks.pocketcontext.com** on the existing ARM64 ONCE host. The administration dashboard is at `/_/`; this service has no dedicated issue-tracker frontend.

## Verified release

- Application source: `409bdc0` on `main`.
- PocketContext pin: `381f81042586afdaa6498b8c0e2a78229a55bdff`.
- Image: `ghcr.io/pocketcontext/taskcontext@sha256:ecbcc47fb2a44a6f9b0d90c820b4596ea2166a320777f6335561434089825c42`.
- [Container CI 35835310114](https://github.com/pocketcontext/taskcontext/actions/runs/35835310114) passed application, portable skill, deployment, startup configuration, persistence, crash-restore, and shutdown-sync restore checks. Native AMD64 and ARM64 images are published.
- The existing ONCE host successfully pulled the release image. No registry login was configured for this release.
- PocketContext tests/build and all three TaskContext Python suites passed locally against the pinned server.

## Infrastructure

The local unversioned `../once-pocketcontext/colors.yml` follows `ghcr.io/pocketcontext/taskcontext:latest`, names the GitHub repository, and retains one CPU, 512 MiB, and the TaskContext environment mappings. The immutable image above records the initial release. Build and dry-run validation passed. A reviewed targeted DNS plan added exactly one proxied A record for `tasks.pocketcontext.com` pointing to the existing host and stored it in the existing DNS backend. No full convergence, compute change, SMTP change, or deployment-key rotation occurred.

The replica is private bucket `taskcontext-backup`, prefix `once-pocketcontext/taskcontext`, using the existing account's EU R2 endpoint. Authenticated access was verified before deployment, when the prefix was empty. Nonempty Litestream LTX objects were verified after startup. `.envrc.private` contains the operator/R2 variables and is mode 0600. Operator credentials match the existing DealContext operator account as requested; credential values are not stored in this repository.

## Deployment and verification

The immutable image was deployed over SSH with `once deploy`, host `tasks.pocketcontext.com`, `--auto-update=false`, one CPU, and 512 MiB, passing only TaskContext's mapped environment values. No deployment keys were regenerated and sibling applications were not converged.

Verified public HTTPS `/up`, administrator authentication, the application schema with `users` and no `agents`, rejected anonymous SQL/schema requests, application URL, trusted proxy, enabled rate limits and batch writes. Docker inspection confirmed a running container, 536870912 memory bytes, 1000000000 NanoCpus, and disabled automatic updates. Inspect only selected metadata fields: ONCE's Docker labels contain credentials.

The users and business collections are empty, as expected for this greenfield service. No synthetic records were written to production. Provision ordinary `users` accounts through the standard PocketBase records API or administration dashboard. User operations and recovery behavior were tested in isolated local/CI databases.

## Continuous deployment

A dedicated TaskContext key was added without replacing sibling deployment keys. Its forced command invokes the root-owned `/usr/local/sbin/deploy-taskcontext` wrapper with a narrow sudo permission. GitHub environment `once-pocketcontext` holds the key and pinned server identity; repository variable `COLORS_PROFILE` enables the deploy job.

The restricted SSH path successfully performed the initial controlled switch from the pinned image to `latest`, retaining one CPU, 512 MiB, data volume, environment and replica. ONCE automatic updates remain disabled. The wrapper pulls first, gracefully stops the sole TaskContext container, then updates. Reinstall `deploy/install.py` after any scaffold convergence that regenerates authorized keys. Never print Docker labels or environment metadata.

## Future updates

Normal releases use CD. For manual rollback, pull the recorded immutable image before stopping anything. Gracefully stop the exact TaskContext container and verify clean exit before `once update tasks.pocketcontext.com --image <digest> --auto-update=false --cpus 1 --memory 512`. ONCE v0.3.3 otherwise overlaps database/Litestream writers. Keep credentials and the replica prefix unchanged. Never run a restored replica beside an active writer. Record the released digest and health verification here after each deployment.
