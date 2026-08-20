<!-- SPDX-License-Identifier: Apache-2.0 -->

# Policy-pack extension template

1. Copy this directory and edit `pack.yaml`: your rules, scope, effective dates,
   evidence, owner, and embedded tests. The rule language is declarative and
   fail-closed; see `docs/extension-sdk.md`.
2. Edit `extension.yaml` identity, description, owner, and compatibility.
   Leave the digests as placeholders.
3. `oak keys init` once, then `oak extensions sign <this directory>` — this
   recomputes payload digests and signs the manifest with the local
   `extension-steward` key.
4. `oak extensions install <this directory>` — the extension lands in
   quarantine.
5. `oak extensions verify extension.<your-id>` — all checks must pass,
   including your embedded tests under the built-in engine.
6. `oak extensions activate extension.<your-id>` — only now can
   `oak policy evaluate --pack pack.<your-id>` use it.
