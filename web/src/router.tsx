// SPDX-License-Identifier: Apache-2.0
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";

const RouterContext = createContext<{
  readonly path: string;
  readonly navigate: (to: string) => void;
}>({ path: "/", navigate: () => undefined });

export function RouterProvider({ children }: { readonly children: ReactNode }) {
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (to: string) => {
    if (to !== window.location.pathname) {
      window.history.pushState(null, "", to);
    }
    setPath(to);
  };

  return (
    <RouterContext.Provider value={{ path, navigate }}>
      {children}
    </RouterContext.Provider>
  );
}

export function useRouter() {
  return useContext(RouterContext);
}

export function Link({
  to,
  children,
  className,
  ariaCurrent,
}: {
  readonly to: string;
  readonly children: ReactNode;
  readonly className?: string;
  readonly ariaCurrent?: "page";
}) {
  const { navigate } = useRouter();
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return (
    <a
      href={to}
      onClick={onClick}
      {...(className === undefined ? {} : { className })}
      {...(ariaCurrent === undefined ? {} : { "aria-current": ariaCurrent })}
    >
      {children}
    </a>
  );
}

export function matchPath(
  pattern: string,
  path: string,
): Record<string, string> | null {
  const patternParts = pattern.split("/").filter((part) => part !== "");
  const pathParts = path.split("/").filter((part) => part !== "");
  if (patternParts.length !== pathParts.length) {
    return null;
  }
  const parameters: Record<string, string> = {};
  for (let index = 0; index < patternParts.length; index += 1) {
    const patternPart = patternParts[index];
    const pathPart = pathParts[index];
    if (patternPart === undefined || pathPart === undefined) {
      return null;
    }
    if (patternPart.startsWith(":")) {
      parameters[patternPart.slice(1)] = decodeURIComponent(pathPart);
    } else if (patternPart !== pathPart) {
      return null;
    }
  }
  return parameters;
}
