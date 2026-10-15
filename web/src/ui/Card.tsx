// SPDX-License-Identifier: Apache-2.0
import { createElement, type HTMLAttributes, type ReactNode } from "react";

export type CardTone = "normal" | "selected" | "infeasible" | "inset";

/**
 * A lifted surface. `lift` makes it rise on hover; `selected` is the blue of a
 * selection; `infeasible` is dashed coral with its reason inside; `inset` is a
 * recessed well for raw values. Landmark roles and names pass straight through.
 */
export function Card({
  as = "section",
  tone = "normal",
  lift = false,
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLElement> & {
  readonly as?: "section" | "article" | "div" | "li" | "aside" | "form";
  readonly tone?: CardTone;
  readonly lift?: boolean;
  readonly children?: ReactNode;
}) {
  const classes = ["card", `card-${tone}`, lift ? "card-lift" : null, className]
    .filter(Boolean)
    .join(" ");
  return createElement(as, { ...rest, className: classes }, children);
}
