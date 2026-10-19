# Community and trust model

Metin2 Studio unifies the format and workflow for adding add-ons. Users choose which files, repositories and publishers they trust. The platform does not certify publishers, issue trust badges, require accounts or impose mandatory signing. These are intentionally outside the project scope, rather than unfinished launch requirements.

## Keep the workflow small

A creator writes original source, builds a manifest-based ZIP and shares that file or a static HTTPS catalog. A player imports the file or subscribes to the catalog, reads the package/source information and reviews the installation plan. Both paths use the same compatibility, ownership, settings and recovery behavior. Neither import nor download automatically installs code.

Studio checks bounded package contents, declared payload hashes and the exact reviewed file changes. A passing check means the package is structurally intact and the proposed operation is consistent; it does not endorse the author or certify gameplay behavior. Add-ons run with the game client’s permissions. The decision to install belongs to the user.

## Sharing and discovery

Local packages and creator-hosted repositories already work without a central service. An optional project-hosted discovery catalog can collect links and original packages later. It needs an actual repository/hosting owner and a support/reporting destination. It does not need an identity service or publisher approval program.

For project-hosted material, keep readable source, an explicit license, release notes and exact version/archive hashes. Do not distribute game packs, executables, installation keys, extracted game source or game artwork without distribution rights. Keep attribution and the relationship with the original Singleplayer project clear; no official partnership or endorsement has been established here.

Use named namespaces to avoid collisions. If an add-on is abandoned, maintain a fork under a new id with the original attribution/license, or record an agreed transfer. Studio shows repository source switches explicitly. Namespace conventions organize packages; they are not publisher identity checks.

## Compatibility and support

Record the manager/client/server versions and evidence level: validator, fixture lifecycle, actual-pack lifecycle, native startup or interactive gameplay. Keep those levels distinct. The current creator tooling has automated rehearsals; independent creator/setup trials and interactive gameplay acceptance remain pending.

Before inviting a wider test group, finish browser/gameplay acceptance, run an independent creator trial and publish understandable setup/recovery instructions and support boundaries. If a shared discovery catalog is created, choose its hosting/maintenance ownership and contribution rules. No public hosting, accounts or outreach have been created by this local development work.

## Withdrawn and changed releases

A repository release version keeps its original archive hash. Publish corrected bytes under a new version. Mark an unwanted release withdrawn with a reason while retaining its immutable record. A successful later catalog check blocks new use; existing installed code can still be configured, disabled or removed. Offline clients learn withdrawal when they check again. Studio does not remotely disable running code.

Local development can reimport a changed build, including one with the same version, because the user explicitly selects that file and reviews a separate update. Published repository versions remain immutable. Preserve cached/installed payloads and recovery data instead of deleting them during an incident.
