"use client";
import { useEffect, useState } from "react";

type Props = {
  request: (path: string, init?: RequestInit) => Promise<unknown>;
  download: (path: string, filename: string) => Promise<void>;
  onDeleted: () => Promise<void>;
};
type Consent = { enabled: boolean; version: number; scope: string };
export default function PrivacyPanel({ request, download, onDeleted }: Props) {
  const [consent, setConsent] = useState<Consent | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    request("me/consent")
      .then((value) => {
        if (active) setConsent(value as Consent);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [request]);
  async function perform(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>Privacy and data controls</h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <p>
        Export and deletion require a login within the last five minutes.{" "}
        <a href="/api/v1/auth/login">Sign in again</a> before a sensitive
        operation.
      </p>
      <p>
        <a href="/api/v1/auth/login?configure_mfa=true">
          Set up authenticator MFA in Keycloak
        </a>
        . Credentials and recovery are managed by your identity provider.
      </p>
      <button
        disabled={busy}
        onClick={() =>
          void perform(() => download("me/export", "pesopilot-data.json"))
        }
      >
        Export all data (JSON)
      </button>{" "}
      <button
        disabled={busy}
        onClick={() =>
          void perform(() =>
            download("me/export?format=csv", "pesopilot-transactions.csv"),
          )
        }
      >
        Export transactions (CSV)
      </button>
      <h3>Model processing</h3>
      <p>
        Category suggestions and statistics run locally without external
        sharing. Optional model assistance requires your explicit opt-in.
        External hosted services are disabled.
      </p>
      {consent && (
        <label className="check">
          <input
            aria-label="Allow local model processing"
            type="checkbox"
            checked={consent.enabled}
            disabled={busy}
            onChange={(event) => {
              const enabled = event.target.checked;
              const previous = consent;
              setConsent({ ...consent, enabled });
              void perform(async () => {
                try {
                  const value = await request("me/consent", {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      enabled,
                      version: previous.version,
                    }),
                  });
                  setConsent(value as Consent);
                  setNotice("Model preference saved.");
                } catch (error) {
                  setConsent(previous);
                  throw error;
                }
              });
            }}
          />
          Allow configured local model to select evidence. {consent.scope}
        </label>
      )}
      <h3>Delete application data</h3>
      <p>
        This removes your active PesoPilot accounts, transactions, transfers,
        refunds, budgets, consent and sessions. Your Keycloak account remains.
        Operator backups follow their configured retention; production backup
        erasure has not been verified.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const confirmation = new FormData(event.currentTarget).get(
            "confirmation",
          );
          if (confirmation !== "DELETE MY DATA") {
            setError("Type DELETE MY DATA exactly.");
            return;
          }
          if (!window.confirm("Permanently delete your active PesoPilot data?"))
            return;
          void perform(async () => {
            await request("me", {
              method: "DELETE",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ confirmation }),
            });
            await onDeleted();
          });
        }}
      >
        <label>
          Deletion confirmation
          <input
            name="confirmation"
            required
            placeholder="DELETE MY DATA"
            autoComplete="off"
          />
        </label>
        <button disabled={busy}>Delete my application data</button>
      </form>
    </section>
  );
}
