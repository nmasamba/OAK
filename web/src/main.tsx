// SPDX-License-Identifier: Apache-2.0
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { getVersion } from "./generated/api";
import { CaseListPage } from "./pages/CaseListPage";
import { CasePage } from "./pages/CasePage";
import { ConfirmPage } from "./pages/ConfirmPage";
import { OperationPage } from "./pages/OperationPage";
import { ReviewPage } from "./pages/ReviewPage";
import { Link, RouterProvider, matchPath, useRouter } from "./router";
import "./styles.css";

function Routes() {
  const { path } = useRouter();

  useEffect(() => {
    const heading = document.getElementById("page-heading");
    if (heading !== null) {
      heading.setAttribute("tabindex", "-1");
      heading.focus();
    }
  }, [path]);

  const reviewMatch = matchPath("/cases/:caseId/review", path);
  if (reviewMatch?.["caseId"] !== undefined) {
    return <ReviewPage caseId={reviewMatch["caseId"]} />;
  }
  const confirmMatch = matchPath("/cases/:caseId/confirm", path);
  if (confirmMatch?.["caseId"] !== undefined) {
    return <ConfirmPage caseId={confirmMatch["caseId"]} />;
  }
  const caseMatch = matchPath("/cases/:caseId", path);
  if (caseMatch?.["caseId"] !== undefined) {
    return <CasePage caseId={caseMatch["caseId"]} />;
  }
  const operationMatch = matchPath("/operations/:operationId", path);
  if (operationMatch?.["operationId"] !== undefined) {
    return <OperationPage operationId={operationMatch["operationId"]} />;
  }
  if (path === "/") {
    return <CaseListPage />;
  }
  return (
    <>
      <h1 id="page-heading">Page not found</h1>
      <p>
        <Link to="/">Back to all cases</Link>
      </p>
    </>
  );
}

function App() {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    getVersion()
      .then((information) => setVersion(information.version))
      .catch(() => setVersion(null));
  }, []);

  return (
    <RouterProvider>
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <header className="masthead">
        <nav aria-label="Primary">
          <Link to="/" className="wordmark">
            OAK Community
          </Link>
        </nav>
        <p className="masthead-meta">
          {version === null ? "API unavailable" : `v${version}`} · local
          non-production workspace
        </p>
      </header>
      <main id="content">
        <div className="page">
          <Routes />
        </div>
      </main>
      <footer className="boundary-footer">
        <p>
          This workspace has no target mutation, secret resolution, or
          inference-traffic path. Compiled plans stay draft review artifacts.
        </p>
      </footer>
    </RouterProvider>
  );
}

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Application root is missing");
}
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
