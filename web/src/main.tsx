// SPDX-License-Identifier: Apache-2.0
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { getModels, type ModelStatusResponse } from "./generated/api";
import { getVersion } from "./generated/api";
import { MODEL_SETTINGS_CHANGED, currentModelToken } from "./modelToken";
import { describeVerdict } from "./ModeSelect";
import { asObject, asString } from "./support";
import { BundlePage } from "./pages/BundlePage";
import { CandidatesPage } from "./pages/CandidatesPage";
import { CaseListPage } from "./pages/CaseListPage";
import { CasePage } from "./pages/CasePage";
import { ConfirmPage } from "./pages/ConfirmPage";
import { DecisionPage } from "./pages/DecisionPage";
import { OperationPage } from "./pages/OperationPage";
import { ReportPage } from "./pages/ReportPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { Link, RouterProvider, matchPath, useRouter } from "./router";
import { Icon } from "./ui/Icon";
// Self-hosted fonts (OFL-1.1), bundled by Vite and served same-origin: no CDN.
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./tokens.css";
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
  const candidatesMatch = matchPath("/cases/:caseId/candidates", path);
  if (candidatesMatch?.["caseId"] !== undefined) {
    return <CandidatesPage caseId={candidatesMatch["caseId"]} />;
  }
  const decisionMatch = matchPath("/cases/:caseId/decision", path);
  if (decisionMatch?.["caseId"] !== undefined) {
    return <DecisionPage caseId={decisionMatch["caseId"]} />;
  }
  const reportMatch = matchPath("/cases/:caseId/report", path);
  if (reportMatch?.["caseId"] !== undefined) {
    return <ReportPage caseId={reportMatch["caseId"]} />;
  }
  const bundleMatch = matchPath("/cases/:caseId/bundle", path);
  if (bundleMatch?.["caseId"] !== undefined) {
    return <BundlePage caseId={bundleMatch["caseId"]} />;
  }
  const caseMatch = matchPath("/cases/:caseId", path);
  if (caseMatch?.["caseId"] !== undefined) {
    return <CasePage caseId={caseMatch["caseId"]} />;
  }
  const operationMatch = matchPath("/operations/:operationId", path);
  if (operationMatch?.["operationId"] !== undefined) {
    return <OperationPage operationId={operationMatch["operationId"]} />;
  }
  if (path === "/settings/models") {
    return <SettingsPage />;
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

/**
 * What the masthead says about interpretation.
 *
 * Read once at load with whatever token this browser holds. Without a token the workspace
 * cannot read model settings at all, and says so rather than implying determinism it has
 * not verified.
 */
function useInterpreterLabel(path: string): string | null {
  const [label, setLabel] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  // The settings page changes the answer without navigating, so a route change alone is
  // not enough: a stale "Deterministic interpretation" would tell someone their brief
  // stays on this machine when it no longer does.
  useEffect(() => {
    const onChanged = () => setRevision((current) => current + 1);
    window.addEventListener(MODEL_SETTINGS_CHANGED, onChanged);
    return () => window.removeEventListener(MODEL_SETTINGS_CHANGED, onChanged);
  }, []);

  useEffect(() => {
    const token = currentModelToken();
    if (token === null) {
      setLabel(null);
      return;
    }
    getModels(token)
      .then((status: ModelStatusResponse) => {
        const online = asObject(status.modes["online"] ?? null);
        const pair = online === null ? null : asObject(online["pair"]);
        const model = pair === null ? null : asString(pair["model_id"]);
        const route = pair === null ? null : asString(pair["provider_route"]);
        const verification =
          online === null ? null : asObject(online["verification"]);
        const verdict =
          verification === null ? null : asString(verification["verdict"]);
        const checkedAt =
          verification === null ? null : asString(verification["checked_at"]);
        const tokenText = describeVerdict(
          verdict,
          checkedAt,
          verification?.["stale"] === true,
        );
        setLabel(
          model === null
            ? `Online AI: not set up · ${tokenText}`
            : `Online AI: ${model}${route === null ? "" : ` via ${route}`} · ${tokenText}`,
        );
      })
      .catch(() => setLabel(null));
  }, [path, revision]);

  return label;
}

function AppShell() {
  const { path } = useRouter();
  const [version, setVersion] = useState<string | null>(null);
  const interpreter = useInterpreterLabel(path);

  useEffect(() => {
    getVersion()
      .then((information) => setVersion(information.version))
      .catch(() => setVersion(null));
  }, []);

  return (
    <>
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <header className="masthead">
        <Link to="/" className="wordmark">
          OAK
        </Link>
        <span className="spacer" />
        <nav aria-label="Primary" className="masthead-nav">
          <Link
            to="/"
            className="ico"
            {...(path === "/" ? { ariaCurrent: "page" as const } : {})}
          >
            <Icon name="cases" size={22} />
            <span className="visually-hidden">Cases</span>
          </Link>
          <Link
            to="/settings/models"
            className="ico"
            {...(path === "/settings/models"
              ? { ariaCurrent: "page" as const }
              : {})}
          >
            <Icon name="models" size={22} />
            <span className="visually-hidden">Models</span>
          </Link>
        </nav>
        <p className="masthead-meta" title="Local, non-production workspace">
          {version === null ? "API unavailable" : `v${version}`} · local
          {interpreter === null ? "" : ` · ${interpreter}`}
        </p>
      </header>
      <main id="content">
        <div className="page">
          <Routes />
        </div>
      </main>
      <footer className="boundary-footer">
        <p>
          Signing, approving and installing happen only in your terminal. By
          default, nothing leaves this machine.
        </p>
      </footer>
    </>
  );
}

function App() {
  return (
    <RouterProvider>
      <AppShell />
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
