# Developers' guide

This guide records repository-wide development practices. More specialized
guidance remains in the documents linked from the
[documentation index](contents.md).

## Spelling policy

Run `make spelling` to enforce en-GB-oxendict spelling in maintained Markdown
prose. The generated `typos.toml` starts from the shared estate dictionary,
refreshes its untracked local cache only when the authority is newer, and then
applies the narrow repository policy in `typos.local.toml`. Edit the local
policy and regenerate the configuration rather than changing generated entries
by hand.

`scripts/typos_rollout_http.py` owns shared-cache freshness, HTTPS transport
security and persistence coordination. Only `scripts/typos_rollout.py` may
compose it with dictionary validation; infrastructure scripts must not reuse
these spelling-policy internals.
