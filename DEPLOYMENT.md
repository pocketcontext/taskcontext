# Deployment record

## Google Workspace JIT — 23 September 2026

Application commit `d0fa646` was deployed with image
`ghcr.io/pocketcontext/taskcontext@sha256:32c298d6311471c9221dcefbb75ca599b4f3dfec0d663712ed97289f5fe231f2`.
[Container CI and deployment](https://github.com/pocketcontext/taskcontext/actions/runs/35905523910)
passed application, OAuth/JIT, disabled-account, realtime revocation, smoke,
restore, both architecture builds, publication, and public health checks.
All Python suites and the pinned-server build also passed locally.

A targeted environment update under the deployment lock gracefully stopped the
old container before replacement. `TASKCONTEXT_GOOGLE_WORKSPACE_DOMAIN` is
`pocketcontext.com`; `TASKCONTEXT_REQUIRED_USERS` is `[]`. The existing Google
credentials, all other environment values, resources, disabled automatic updates,
and sibling containers were preserved. Alberto's account remains active with ID
`konw1lekaa9nl37`; it is no longer provisioned at startup. Verified live Google
provider enablement, password availability, OAuth-only signup rule, disabled-user
auth rule, seven-day token duration, and public `/up` health. No synthetic users
were created in production. First-login JIT and rejection cases were tested using
an isolated synthetic Google provider; a real existing-user login had previously
been confirmed by the user.

User records now cannot be deleted. Disable access using the operator-managed
`disabled` field to preserve attribution and revoke sessions. This migration is
not reversible through an automatic migration rollback; use a deliberate backup
restore if rollback is required.

The records below describe the original release.

## First release deployment

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

The first full CD run [35839474799](https://github.com/pocketcontext/taskcontext/actions/runs/35839474799) passed tests, restore checks, both architecture builds, publication, SSH deployment, and public health verification. Live inspection confirmed application revision `3fd57a8`, one running TaskContext container using `latest`, preserved resource limits, and disabled automatic updates. Sibling application health checks passed.

The run also covers leading-hyphen operator passwords: the entrypoint separates positional credentials with `--`, and smoke/restore fixtures deliberately exercise that case.

## Future updates

Normal releases use CD. For manual rollback, pull the recorded immutable image before stopping anything. Gracefully stop the exact TaskContext container and verify clean exit before `once update tasks.pocketcontext.com --image <digest> --auto-update=false --cpus 1 --memory 512`. ONCE v0.3.3 otherwise overlaps database/Litestream writers. Keep credentials and the replica prefix unchanged. Never run a restored replica beside an active writer. Record the released digest and health verification here after each deployment.
