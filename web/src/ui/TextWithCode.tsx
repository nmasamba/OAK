// SPDX-License-Identifier: Apache-2.0
import { Fragment } from "react";

/**
 * A sentence from the API whose `backticked` spans name a command, shown with those spans
 * as code rather than as literal backticks. The API's reasons are shared with the CLI,
 * which prints them as they are. Text with an unbalanced backtick is shown unchanged.
 */
export function TextWithCode({ text }: { readonly text: string }) {
  const parts = text.split("`");
  if (parts.length % 2 === 0) {
    return <>{text}</>;
  }
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <code key={index}>{part}</code>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  );
}
