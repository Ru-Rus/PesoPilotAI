"use client";
import { useEffect, useState } from "react";

type Session = {
  id: string;
  current: boolean;
  created_at: string;
  expires_at: string;
  last_seen_at: string;
};
type Props = {
  request: (path: string, init?: RequestInit) => Promise<unknown>;
  onChange: () => Promise<void>;
};

export default function SessionPanel({ request, onChange }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    let active = true;
    request("auth/sessions")
      .then((rows) => {
        if (active) setSessions(rows as Session[]);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [request]);
  async function revoke(item: Session) {
    if (
      !window.confirm(
        item.current ? "Sign out of this session?" : "Revoke this session?",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await request(`auth/sessions/${item.id}`, { method: "DELETE" });
      setSessions((previous) => previous.filter((s) => s.id !== item.id));
      if (item.current) await onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>Your active sessions</h2>
      <p>
        Revoking an application session signs that browser out of PesoPilot.
        Provider sessions are managed in Keycloak.
      </p>
      {busy && <p role="status">Updating sessions…</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {sessions.map((item) => (
        <div key={item.id} className="account-row">
          <div>
            <strong>{item.current ? "This browser" : "Another session"}</strong>
            <small>Started {new Date(item.created_at).toLocaleString()}</small>
            <small>Expires {new Date(item.expires_at).toLocaleString()}</small>
          </div>
          <button disabled={busy} onClick={() => void revoke(item)}>
            {item.current ? "Sign out here" : "Revoke"}
          </button>
        </div>
      ))}
    </section>
  );
}
