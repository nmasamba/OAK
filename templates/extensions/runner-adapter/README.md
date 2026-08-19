<!-- SPDX-License-Identifier: Apache-2.0 -->

# Runner-adapter extension template

A new runner adapter is contributed as reviewed in-tree source: register its
identity, version, digest, parameter schema, and kind allowlist in
`oak.domain.runner_adapters`, implement fixed allowlisted argv construction
with `shell=False`, and pass the argv-safety and rollback checks in
`tests/extension_kit`. The runner independently re-verifies all of it before
any target access — an extension can never widen that trust.

This extension class only documents and configures a registered adapter:

1. Edit `adapter.yaml` to bind a `runner_adapter_id`.
2. Edit `extension.yaml`, then `oak extensions sign`, `install`, `verify`,
   `activate`.
