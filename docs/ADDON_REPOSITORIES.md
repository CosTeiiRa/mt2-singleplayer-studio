# GitHub repositories, catalogs and reviewed downloads

Studio alpha-1.7.0 can subscribe to public GitHub source repositories and creator-hosted HTTPS catalogs. No official community catalog is hosted or subscribed by default. You do not need an account, and Studio does not publish anything on your behalf.

Start with the [Add-on README](../addonhub/README.md) for creation/import instructions. GitHub repositories and catalog URLs share Discover, download reviews, the immutable package cache and the existing sandbox installer.

## Player workflow

1. Open **Add-ons → Repositories** and add a public GitHub repository URL or catalog URL supplied by a creator you trust. Adding fetches metadata only.
2. Choose stable releases, include prereleases, or explicitly select the GitHub Development branch. **Check for updates** fetches the index when requested. Opening Studio, refreshing the local view and changing channels do not perform a network check. Check after changing channels to refresh the selected branch/release metadata. GitHub download review also resolves the selected reference and reads its pinned manifest/README.
3. In **Discover**, choose a repository release and **Review download**. Inspect the source, version, exact URL and release notes. Catalogs provide the archive size/hash. GitHub reviews show the full pinned commit, manifest hash and README; the normalized package size/hash become known after download and validation. You decide whether to trust the package and publisher. If an add-on changes repositories, an additional source-change acknowledgement is required.
4. **Download and verify** caches the archive and validates its manifest and payloads. It neither installs nor executes client code. The selected release becomes available in the local catalog.
5. In an owned pack sandbox, review a separate install or update plan. Apply it only after reviewing compatibility and file changes. Downloading an update leaves the installed version and settings untouched until this step.

Disabling/removing a repository excludes its releases from new installations, updates and enabling. Existing installed code remains available for configuration, disabling and removal. Removal of a repository retains cached releases, checksums, installed payloads and recovery records. Withdrawal blocks new use after the next successful catalog check; it does not remotely stop already enabled code. Offline clients cannot learn a new withdrawal until they check again.

If checking fails, Studio retains the last valid metadata and shows the error. Only archives already cached and verified can be selected while that error remains. Cached bytes are verified again before selection. If two enabled sources offer the same id, disable the competing source before selecting it. Remote packages cannot replace the bundled example ids.

## Manual update notifications and changelogs

**No add-on is automatically downloaded, installed or updated.** Installed's **Check for updates** submits one `repositories/check-updates` job with empty data. It checks enabled sources sequentially, collects per-source failures and publishes metadata only. Cancellation discards the prepared batch. Source add, explicit checks and download reviews are the only paths that fetch publisher metadata; opening views does not perform a remote check.

GET `/api/addons/updates` computes notices from installed records, last-known offers and selected packages, without network access or state mutation. Notices include installed/available versions and commits, last successful check time, cached changelog entries, source errors and whether the package is already selected for installation review. Repository notifications match the installed source/channel, excluding blocked/competing sources. Legacy records are associated only when their installed digest still matches the selected source. Locally selected changes remain explicitly reviewable.

Studio displays counts in its overview/add-on toolbar and a list in Installed. **Read changelog** opens cached notes without creating a download or installation plan. Notes cover known releases newer than the installed version; withdrawn intermediate releases are marked. GitHub release bodies and manifest development/local `release_notes` are shown as escaped text. This is bounded known history, not a generated diff or a complete project changelog.

**Not now** closes the changelog. **Review download** starts a separate pinned review; the user must choose download. A downloaded package still requires **Review installation changes → Apply**. Notifications remain while installed bytes are unchanged. Failed checks show last-known availability and errors; unavailable uncached downloads stay disabled. No update-all/apply-all operation, unattended timer or automatic retry is introduced.

## GitHub source format and release selection

Use `https://github.com/owner/repository` (a trailing slash or `.git` suffix is normalized). Branch/file URLs and credential/query URLs are rejected. A single-add-on repository uses root `addon.json` and declared `payload/` files. A collection uses root `addons.json` listing independent add-on folders, described below. A UTF-8 `README.md` is optional, limited to 256 KiB and displayed as escaped text. Private repositories, undeclared layouts, Git submodules/LFS pointer expansion and arbitrary build systems are unsupported.

Published GitHub Releases with SemVer tags are discovered from the first 50 API records. Single-add-on tags use `v1.2.0` or `1.2.0`; collection tags use the full add-on id, such as `yourname.atlas/v1.2.0`. A lowercase `v` prefix is optional before the version, which must exactly match that add-on's `addon.json`. The 50-record limit is per repository, shared by all members. Drafts and non-SemVer tags are ignored. Stable excludes GitHub-marked or SemVer prereleases. Include prereleases includes both. Bare tags without a GitHub Release do not enter discovery. GitHub Releases need no uploaded add-on archive.

Development is an explicit separate channel that follows the repository's default branch, with the manifest's version and a full commit SHA in review. It does not silently enter stable/prerelease lists. Updates compare the discovered package digest with the installed package: downloading a new build does not make it appear installed, and a README-only commit does not require reinstalling unchanged payloads. Check after switching channels to discover the current revision.

Studio resolves a selected tag/branch to a commit, fetches the archive for that commit and normalizes only `addon.json` and its declared files through the ordinary artifact builder. Unlisted source/development files are not staged. No build scripts or add-on code run. The source ZIP is bounded to 66 MiB and 20,000 entries; ordinary declared-file limits apply. Payload hashes and the reviewed manifest are rechecked before selection. The resulting canonical archive hash appears in package details; a commit pin is source identity, not publisher certification.

An observed release version must keep the same commit; collection observations are scoped to the add-on id. A moved tag blocks new use from that repository until the original reference is restored and successfully checked; removing/readding the subscription retains this observation. A failed check keeps the last good metadata and permits only already cached downloads. Removing a GitHub Release makes it unavailable after the next check (deleting a Git tag alone does not erase a published release). No remote action removes already installed code. Cached older versions remain selected only while policy still allows them.

No GitHub credentials are stored or sent. API rate/refusal errors explain that the public limit may require retrying later. The provider constructs public GitHub API/raw/codeload URLs and uses the same bounded HTTPS transport described below. An inaccessible manifest, mismatched release version or unsupported layout fails clearly rather than guessing how to build it.

## GitHub collections

Follow the [collection creation tutorial](../addonhub/README.md#publish-a-collection-from-one-repository). Root `addons.json` has schema version 1, a display `name`, a `publisher`, and an `addons` list of `{ "id": "yourname.atlas", "path": "addons/atlas" }` entries. It is bounded to 256 KiB and 1–20 unique ids. Folders must be confined relative paths, distinct without case collisions or parent/child overlap. Each folder contains an ordinary `addon.json` and `payload/`; its manifest id must match the declaration. Discovery rejects a root containing both `addon.json` and `addons.json`.

Adding the repository lists each member separately without selecting/downloading any member. Each has independent versions, changelogs, selected packages, installation, settings and enabled state. The repository channel is shared. Requirements/conflicts use the normal add-on ids and installation checks; Studio never automatically downloads dependencies or siblings. Members without a qualifying release remain unselectable in Stable/Prerelease; explicitly choose Development for those snapshots.

Published releases must use `<full-addon-id>/v<SemVer>` (optional lowercase `v`). For example, `yourname.atlas/v1.1.0` and `yourname.legend/v2.0.0` can point to the same commit or different commits. Updating one manifest or publishing its tag does not publish another member. Development members share the pinned default-branch commit but compare their own package content; an unchanged sibling gets no update notice.

Discovery reads membership from the current default branch. Review resolves the selected member's own release commit and reads that commit's declaration to locate its folder, so older releases still work after a folder move. The review shows the add-on folder and pins the commit, manifest checksum and collection declaration checksum. The member README is preferred, with root README fallback at that same commit. Archive validation checks the declaration, id/path and selected manifest/payload against that review. Only the selected member's declared files become a normal package; sibling source files and build scripts are not imported or run. GitHub still transports the whole source ZIP, subject to the 66 MiB/20,000-entry bound.

Immutable observations and commit-to-package cache records include the member id. Two members at the same commit therefore retain separate artifacts and settings. Installed provenance retains its applied folder/revision until an installation update applies. Failed checks preserve the last good collection metadata. Removed members are excluded from new use after a successful check while installed configuration, disable/removal and recovery remain available. Removing the whole subscription likewise preserves installed add-ons.

To convert an existing root repository, move the package into a member folder, retain its id, create root `addons.json`, remove root `addon.json` and publish a **new** version with a scoped tag. Do not reuse an observed version for a different commit. Old root-only tags do not become collection releases automatically. Single-add-on repositories continue to use their original format and tags unchanged.

## Local packages without hosting

In **Discover → Import package**, choose the `.m2addon.zip` produced by the creator CLI. Studio validates its manifest, paths and payload hashes and adds it to the same local catalog used by repository downloads. It opens package details with the filename and archive checksum. No repository, account, certification or network request is needed. Review and apply an installation/update plan separately; importing a newer build leaves installed code and saved settings unchanged.

To iterate locally, rebuild into a new ZIP filename and import it again. Even a changed build with the same version has a distinct archive hash and requires an update plan. Published repository releases still require immutable version/hash records. For distribution, publish new bytes as a new version.

**Remove from catalog** forgets the selected local release and retains installed code, cached bytes and recovery data. You can manage installed code in Installed and reimport the file later. Importing a file explicitly selects that source; switching back to a repository still shows the source-change acknowledgement. Both routes retain the existing compatibility and ownership checks.

## Catalog JSON format

Use `python tools/addon.py catalog` to generate an index from actual release archives, rather than entering checksums manually. The editor schema is `addonhub/schemas/repository.schema.json`; the Python validator additionally enforces SemVer, uniqueness, transport and size rules.

```json
{
  "schema_version": 1,
  "name": "Example creator catalog",
  "publisher": "Example creator",
  "packages": [{
    "id": "example.overlay",
    "name": "Example overlay",
    "description": "An original atlas extension.",
    "author": "Example creator",
    "category": "Interface",
    "releases": [{
      "version": "1.0.0",
      "url": "https://example.org/releases/example.overlay-1.0.0.m2addon.zip",
      "sha256": "REPLACE_WITH_ACTUAL_ARCHIVE_SHA256",
      "bytes": 1234,
      "withdrawn": false,
      "release_notes": "Initial release; include concrete compatibility evidence."
    }]
  }]
}
```

The checksum placeholder intentionally fails validation. Each release's size and hash describe the entire ZIP, not its expanded payload or manifest digest. A package version is immutable: once observed, a changed archive hash for that repository/id/version blocks the repository. Removing and re-adding the subscription does not erase this record. Publish corrected bytes under a new version. To withdraw, retain the original hash/size and add `"withdrawn": true` plus a reason. Recovering from an accidental hash mutation requires restoring the original record before a successful check; do not delete state to conceal the change.

Indices are UTF-8 JSON, limited to 2 MiB, 200 packages and 50 releases per package. There are at most 20 subscriptions per world. Duplicate JSON keys, non-finite numbers and nesting deeper than 32 levels are rejected. Versions follow [SemVer 2.0.0](https://semver.org/); build metadata does not affect ordering. Stable excludes prereleases; the prerelease channel includes both.

## Archives and transport

Archives contain only root `addon.json` and the manifest's declared `payload/` files. Compression is ZIP stored/deflate, with no encryption, links, special files, absolute paths, Windows path aliases, traversal or case collisions. Expanded payload is limited to 64 MiB, each file to 16 MiB and the manifest to 256 KiB. Compressed archives have a 66 MiB limit. Artifact construction uses sorted members and fixed timestamps; repeat builds with the same inputs and tool environment produce identical bytes. Cross-version compressor reproducibility is not promised; preserve the published archive.

Transport uses public HTTPS on port 443 with normal certificate/hostname verification. Credentials, IP-literal hosts, local/private DNS answers, HTTPS downgrades and private redirect targets are refused. DNS is resolved and checked before connecting to a pinned public address; TLS verifies the original hostname. Each redirect is checked again, response sizes are bounded, environment proxy settings are not used, and no Studio token/cookie or game data is attached. System DNS resolution remains subject to the operating system resolver. Credentialed/private-network repositories and proxy-based access are unsupported in this alpha.

Studio checks archive integrity and reviewed file changes. Users decide which sources and publishers to trust. The platform does not certify publishers or require signed releases. Client add-ons run with the game client’s permissions; compatibility declarations remain separate from recorded testing. See the [community guide](ADDON_COMMUNITY.md).

## Background work and cancellation

The Studio interface submits repository add/check, download-review and download operations as background jobs. No network request holds the Studio or add-on service lock. A job prepares metadata in a separate working snapshot and shares only immutable cache files. Completion publishes metadata only if the original repository fingerprint still matches; an external edit causes prepared changes to be rejected. Failed checks may publish their last-good metadata plus the check error, preserving installed payloads/settings.

One job may run per world. Other add-on mutations, including import, target changes and installation plans, are refused while it is active; reads and unrelated server work remain available. Starting and finishing a job invalidate installation plans. Source-switch acknowledgement and commit/package checks still apply. A background download never installs automatically.

Cancellation is cooperative: the worker checks before/after each request and while receiving chunks. An in-flight DNS/connect/read can take until its transport timeout to return. Until the worker finishes, the panel shows cancellation requested and other add-on mutations remain paused. Accepted cancellation discards the working metadata and selections; completed immutable cache bytes may remain. No thread is forcibly killed. There is no automatic retry or resume, including after restart.

Job history retains 20 status summaries in `repository-jobs.json`, without request inputs or result bodies. Running/queued records become interrupted on startup. Review results are available only in the current process while their review remains valid. Refresh/navigation reconnects UI polling to the current job. This polling reads local status only; it does not automatically check remote releases.

## API and storage

All routes share Studio's local origin/session. Mutations require `X-Studio-Token`. The UI uses `jobs/start` for network operations. Direct network routes below remain synchronous for compatibility; they are also refused while a job is active.

| Route below `/api/addons/` | Method and purpose |
| --- | --- |
| `updates` | GET cached manual update notices/changelogs; no network or selection changes |
| `repositories` / `releases` | GET subscription status and locally known offers; no network |
| `jobs/start` | POST `operation` and `data`; returns HTTP 202 with a job for repository add/refresh, `repositories/check-updates` (empty data), release review or release download |
| `job?id=<id>` / `jobs` | GET a job/result or the last 20 summaries; no network |
| `jobs/cancel` | POST `job_id`; request cooperative cancellation |
| `repositories/add` | POST `url`, optional `channel`; subscribe and fetch metadata |
| `repositories/refresh` | POST `repository_id`; explicitly check metadata |
| `repositories/configure` | POST `repository_id`, optional `enabled`/`channel` |
| `repositories/remove` | POST `repository_id`; remove subscription only |
| `releases/review` | POST `repository_id`, `addon_id`, `version`; obtain a download review |
| `releases/download` | POST `review_id`, optional `accept_source_change`; verify/cache only |
| `packages/import` | POST raw `application/zip`, known Content-Length ≤66 MiB and URL-encoded `X-Addon-Filename`; validate/cache a local file |
| `packages/forget` | POST `addon_id`; remove a local catalog selection, retaining installed code/cache/recovery |
| `plan` / `apply` | Existing separate sandbox installation review and transaction |
| `support-report` | GET allowlisted diagnostics without paths, settings, URLs or game content |

Under the world's private `addons/`, `repositories.json` records subscriptions, last valid indices, observed immutable hashes/commits and selected releases, including local file names/source kinds. GitHub commit-to-artifact metadata is cached alongside subscriptions, scoped to the member id for collections; installed records separately retain their applied source revision. `artifacts/<sha>.zip` and `releases/<sha>/` retain verified bytes. Per-target installed objects/baselines/journals remain separate. Repository changes invalidate both download and installation reviews, including changes detected in persisted state. Source path/payload changes also remain subject to the existing manager checks.

Background jobs are implemented for the interface and job API. The compatible direct network routes retain their earlier synchronous behavior. Cache pruning and automatic remote update checks remain unimplemented. Preserve the state folder for recovery; manually deleting caches or repository records is not an uninstall procedure.

Example background request (shared Studio session required):

```json
{"operation":"repositories/refresh","data":{"repository_id":"THE_SUBSCRIBED_ID"}}
```

POST it to `/api/addons/jobs/start`, retain `job.id`, and poll `/api/addons/job?id=<id>` until `status` leaves `queued`/`running`. A successful detail response contains `result` with the ordinary route's response fields, such as `review` or `downloaded`. Handle `failed`, `cancelled` and `interrupted` explicitly. Enqueue success means accepted work, not a completed check or installation.
