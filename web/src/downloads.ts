// SPDX-License-Identifier: Apache-2.0
/**
 * One-tap downloads. A stored artifact is fetched as raw bytes through the existing
 * artifact read, hashed in the browser with SubtleCrypto, and saved only when its
 * sha256 equals the digest the server sent in `X-OAK-Artifact-Digest`. Parsed JSON is
 * never re-serialised: JavaScript would drop the `.0` of a whole-number float and the
 * digest would stop matching. A download authorises nothing.
 */
import {
  getArchitectureDocument,
  getArtifactBytes,
  type ArtifactReference,
} from "./generated/api";

/** `verified` means the bytes hashed to the server's digest; `saved` means a file with no
 * digest of its own (the composed document, the drawn diagram) was written, unchecked. */
export type DownloadState =
  | "idle"
  | "fetching"
  | "verified"
  | "saved"
  | "mismatch"
  | "failed";

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function saveText(
  text: string,
  mediaType: string,
  filename: string,
): void {
  saveBlob(new Blob([text], { type: mediaType }), filename);
}

/** The file extension a media type is saved under. */
export function extensionFor(mediaType: string): string {
  const type = mediaType.split(";")[0]?.trim().toLowerCase() ?? "";
  if (type.endsWith("yaml") || type.endsWith("yml")) {
    return "yaml";
  }
  if (type.endsWith("json")) {
    return "json";
  }
  if (type === "text/markdown") {
    return "md";
  }
  if (type === "image/svg+xml") {
    return "svg";
  }
  return "txt";
}

/**
 * Fetches, verifies and saves one stored artifact. Resolves to `verified` once the file
 * is saved, or `mismatch` when the bytes do not hash to the digest the server named, in
 * which case nothing is saved. Any transport failure rejects.
 */
export async function downloadVerified(
  caseId: string,
  reference: ArtifactReference,
  filename: string | null,
): Promise<"verified" | "mismatch"> {
  const fetched = await getArtifactBytes(caseId, reference);
  const expected = (fetched.digest ?? reference.digest)
    .replace(/^sha256:/i, "")
    .toLowerCase();
  const actual = await sha256Hex(fetched.bytes);
  if (actual !== expected) {
    return "mismatch";
  }
  saveBlob(
    new Blob([fetched.bytes], { type: fetched.mediaType }),
    filename ?? `${reference.id}.${extensionFor(fetched.mediaType)}`,
  );
  return "verified";
}

/** Saves the composed architecture document. It has no stable digest of its own. */
export async function downloadArchitecture(
  caseId: string,
  format: "json" | "yaml",
  candidateId: string | null,
): Promise<void> {
  const fetched = await getArchitectureDocument(caseId, format, candidateId);
  saveBlob(
    new Blob([fetched.bytes], { type: fetched.mediaType }),
    fetched.filename ?? `${caseId}-architecture.${format}`,
  );
}
