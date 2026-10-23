// SPDX-License-Identifier: Apache-2.0
/**
 * The repository's read-only fixture target (`examples/targets/local-fixture.yaml`) as the
 * JSON the target field takes, so a reader can start from it instead of converting YAML by
 * hand (F3-16). `tests/contract/test_web_fixture_target.py` keeps the two the same.
 */
export const LOCAL_FIXTURE_TARGET_JSON = `{
  "target_profile_version": "0.1.0",
  "id": "target.local-fixture",
  "status": "non-production-fixture",
  "environment": "validation",
  "tenant_id": "local",
  "platform": {
    "operating_system": "linux",
    "architecture": "x86_64",
    "accelerators": [],
    "drivers": [],
    "container_runtime": "rootless-compatible OCI runtime"
  },
  "capacity": {
    "ram_gib": 32,
    "storage_gib": 100
  },
  "network": {
    "mode": "isolated-no-egress",
    "inbound_control_plane": false
  },
  "permissions": {
    "mutation_allowed": false,
    "allowed_operations": [
      "inventory",
      "validate",
      "render",
      "plan",
      "verify"
    ]
  },
  "secrets": {
    "allowed_references": []
  },
  "notes": [
    "Synthetic target for compiler and dry-run tests only."
  ]
}`;
