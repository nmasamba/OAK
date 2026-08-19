<!-- SPDX-License-Identifier: Apache-2.0 -->

# Deployment-adapter extension template

Deployment renderers are in-tree code with pinned identities; this extension
class is the governed, explicit local configuration that binds one. A new
backend is contributed as reviewed source implementing
`DeploymentRendererPort` (see `docs/extension-sdk.md`), never as downloaded
code inside an extension.

1. Edit `adapter.yaml` to bind a registered `renderer_id` and any
   configuration your review needs to record.
2. Edit `extension.yaml` identity and compatibility.
3. `oak extensions sign <dir>`, `install`, `verify`, `activate` as with any
   extension; then `oak render --adapter <renderer_id> --output <dir>`.
