// SPDX-License-Identifier: Apache-2.0
/**
 * The drawn topology as a standalone SVG file. The page paints the diagram with CSS
 * tokens; a file has no stylesheet, so every painted property is copied from the
 * computed style onto the element before serialising. No route is involved.
 */

const PAINTED = [
  "fill",
  "stroke",
  "stroke-width",
  "stroke-linecap",
  "font-family",
  "font-size",
  "font-weight",
] as const;

export function serialiseDiagram(svg: SVGSVGElement): string {
  const copy = svg.cloneNode(true) as SVGSVGElement;
  const sources = [svg, ...svg.querySelectorAll<SVGElement>("*")];
  const targets = [copy, ...copy.querySelectorAll<SVGElement>("*")];
  sources.forEach((source, index) => {
    const target = targets[index];
    if (target === undefined) {
      return;
    }
    const computed = getComputedStyle(source);
    for (const property of PAINTED) {
      const value = computed.getPropertyValue(property);
      if (value !== "") {
        target.style.setProperty(property, value);
      }
    }
    target.removeAttribute("class");
  });
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copy.removeAttribute("id");
  const background = getComputedStyle(svg.parentElement ?? svg).backgroundColor;
  if (background !== "" && background !== "rgba(0, 0, 0, 0)") {
    copy.style.setProperty("background-color", background);
  }
  return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(copy)}\n`;
}
