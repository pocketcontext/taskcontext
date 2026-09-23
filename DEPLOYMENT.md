# First release deployment

Release prepared on 23 September 2026 for `https://tasks.pocketcontext.com` on the existing ARM64 ONCE host. **The application has not started yet:** the TaskContext superuser password is still blank in the private deployment configuration.

## Verified release

- Application source: `409bdc0` on `main`.
- PocketContext pin: `381f81042586afdaa6498b8c0e2a78229a55bdff`.
- Image: `ghcr.io/pocketcontext/taskcontext@sha256:ecbcc47fb2a44a6f9b0d90c820b4596ea2166a320777f6335561434089825c42`.
- [Container CI 35835310114](https://github.com/pocketcontext/taskcontext/actions/runs/35835310114) passed application, portable skill, deployment, startup configuration, persistence, crash-restore, and shutdown-sync restore checks. Native AMD64 and ARM64 images are published.
- The existing ONCE host successfully pulled the release image. No registry login was configured for this release.
- PocketContext tests/build and all three TaskContext Python suites passed locally against the pinned server.

## Infrastructure prepared

The local unversioned `../once-pocketcontext/colors.yml` pins the image, one CPU, 512 MiB, and the TaskContext environment mappings. Build and dry-run validation passed. A reviewed targeted DNS plan added exactly one proxied A record for `tasks.pocketcontext.com` pointing to the existing host and stored it in the existing DNS backend. No full convergence, compute change, SMTP change, or deployment-key rotation occurred.

The replica is private bucket `taskcontext-backup`, prefix `once-pocketcontext/taskcontext`, using the existing account's EU R2 endpoint. Authenticated access was verified and the prefix was empty. `.envrc.private` contains the new operator/R2 variables and is mode 0600. The missing value is `COLORS_PAR_APP_TASKCONTEXT_SUPERUSER_PASSWORD`; keep its value in that file, never Git or chat.

## Initial deployment remaining

Once all configuration values are populated, deploy the immutable image over SSH with `once deploy`, host `tasks.pocketcontext.com`, `--auto-update=false`, one CPU, and 512 MiB. Pass only TaskContext's mapped environment values. Do not regenerate deployment keys or converge sibling applications.

Then verify public `/up`, administrator authentication, the application schema, rejected anonymous SQL, container resource limits, disabled automatic updates, and replica objects. Provision ordinary `users` accounts through the standard PocketBase records API. No demo users or business records should be seeded in this greenfield service.

## Future updates

Pull the tested new immutable image before stopping anything. Gracefully stop the exact TaskContext container and verify clean exit before `once update tasks.pocketcontext.com --image <digest> --auto-update=false --cpus 1 --memory 512`. ONCE v0.3.3 otherwise overlaps database/Litestream writers. Keep credentials and the replica prefix unchanged. Never run a restored replica beside an active writer. Record the released digest and health verification here after each deployment.
