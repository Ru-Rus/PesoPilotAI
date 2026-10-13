"use client";
import { useCallback, useEffect, useRef, useState } from "react";

type Account = {
  id: number;
  name: string;
  kind: string;
  balance_minor: number;
  opening_minor: number;
  archived: boolean;
  version: number;
};
type Transaction = {
  id: number;
  account_id: number;
  occurred_at: string;
  description: string;
  category: string;
  kind: string;
  amount_minor: number;
  version: number;
};
type Summary = {
  income_minor: number;
  expense_minor: number;
  net_minor: number;
  categories: Record<string, number>;
  budgets: {
    id: number;
    category: string;
    limit_minor: number;
    spent_minor: number;
  }[];
};
type Preview = {
  digest: string;
  already_imported: boolean;
  duplicate_candidates: number;
  count: number;
  rows: Transaction[];
};
const categories = [
  "Food & dining",
  "Transport",
  "Shopping",
  "Bills",
  "Health",
  "Entertainment",
  "Income",
  "Other",
];
const money = (n: number) =>
  new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(
    n / 100,
  );
let csrfToken = "";
class APIError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
async function api(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (init?.method && !["GET", "HEAD"].includes(init.method))
    headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch("/api/v1/" + path, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new APIError(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status}). Check your input and backend connection.`,
      response.status,
    );
  }
  return response.status === 204 ? null : response.json();
}
const json = (body: unknown) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export default function Dashboard() {
  const requestGeneration = useRef(0);
  const [user, setUser] = useState<{ id: string; name: string } | null>(null);
  const [tab, setTab] = useState("Overview");
  const [month, setMonth] = useState(() => {
    const parts = new Intl.DateTimeFormat("en", {
      timeZone: "Asia/Manila",
      year: "numeric",
      month: "2-digit",
    }).formatToParts(new Date());
    return `${parts.find((p) => p.type === "year")!.value}-${parts.find((p) => p.type === "month")!.value}`;
  });
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [importAccount, setImportAccount] = useState("");
  const [ack, setAck] = useState(false);
  const reload = useCallback(async () => {
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError("");
    try {
      const identity = await api("auth/me");
      if (generation !== requestGeneration.current) return;
      csrfToken = identity.csrf_token;
      setUser(identity);
      const [a, t, s] = await Promise.all([
        api("accounts"),
        api("transactions?limit=100"),
        api(`analytics/summary?month=${month}`),
      ]);
      if (generation !== requestGeneration.current) return;
      setAccounts(a);
      setTransactions(t);
      setHasMore(t.length === 100);
      setSummary(s);
    } catch (e) {
      if (generation !== requestGeneration.current) return;
      if (e instanceof APIError && e.status === 401) {
        csrfToken = "";
        setUser(null);
        setEditing(null);
        setHasMore(false);
        setAccounts([]);
        setTransactions([]);
        setSummary(null);
        setPreview(null);
      } else setError((e as Error).message);
    } finally {
      if (generation === requestGeneration.current) setLoading(false);
    }
  }, [month]);
  useEffect(() => {
    void reload();
  }, [reload]);
  async function action(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      setNotice(message);
      await reload();
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof APIError && e.status === 401) {
        csrfToken = "";
        setUser(null);
        setEditing(null);
        setHasMore(false);
        setAccounts([]);
        setTransactions([]);
        setSummary(null);
        setPreview(null);
      }
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    ++requestGeneration.current;
    setBusy(true);
    setLoading(false);
    try {
      const result = await api("auth/logout", { method: "POST" });
      csrfToken = "";
      setUser(null);
      setEditing(null);
      setHasMore(false);
      setAccounts([]);
      setTransactions([]);
      setSummary(null);
      setPreview(null);
      setNotice("");
      if (result.logout_url) window.location.assign(result.logout_url);
    } catch (e) {
      setError((e as Error).message);
      await reload();
    } finally {
      setBusy(false);
    }
  }
  async function loadMore() {
    const last = transactions.at(-1);
    if (!last) return;
    const generation = requestGeneration.current;
    setBusy(true);
    try {
      const rows: Transaction[] = await api(
        `transactions?limit=100&before_date=${last.occurred_at}&before_id=${last.id}`,
      );
      if (generation === requestGeneration.current) {
        setTransactions((previous) => [...previous, ...rows]);
        setHasMore(rows.length === 100);
      }
    } catch (e) {
      if (generation === requestGeneration.current) {
        setError((e as Error).message);
        if (e instanceof APIError && e.status === 401) await reload();
      }
    } finally {
      setBusy(false);
    }
  }
  const activeAccounts = accounts.filter((a) => !a.archived);
  const total = accounts.reduce((sum, a) => sum + a.balance_minor, 0);
  const expenseCategories = Object.entries(summary?.categories || {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  const accountSelect = (
    <label>
      Account
      <select name="account_id" required defaultValue="">
        <option value="" disabled>
          Select an account
        </option>
        {activeAccounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </select>
    </label>
  );
  if (!user)
    return (
      <main className="login-page">
        <section className="card login-card">
          <a className="brand" href="/">
            ◈{" "}
            <span>
              PesoPilot<small>PERSONAL FINANCE</small>
            </span>
          </a>
          <h1>Your money, in your hands.</h1>
          <p>Sign in to your private finance workspace.</p>
          {loading ? (
            <p role="status">Checking your session…</p>
          ) : (
            <a className="login-button" href="/api/v1/auth/login">
              Sign in with Keycloak →
            </a>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <p className="login-note">
            Manage your credentials with Keycloak. Your accounts, budgets, and
            transactions belong to you.
          </p>
        </section>
      </main>
    );
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="/">
          ◈{" "}
          <span>
            PesoPilot<small>PERSONAL FINANCE</small>
          </span>
        </a>
        <div className="workspace">
          Your workspace <span>PRIVATE ACCOUNT</span>
        </div>
        <nav aria-label="Main navigation">
          {[
            "Overview",
            "Transactions",
            "Accounts",
            "Budgets",
            "CSV import",
          ].map((name, i) => (
            <button
              key={name}
              className={tab === name ? "active" : ""}
              onClick={() => setTab(name)}
            >
              <span>{["◫", "⇄", "▤", "◎", "↥"][i]}</span>
              {name}
            </button>
          ))}
        </nav>
        <div className="aside-note">
          <span className="spark">✦</span>
          <strong>A little clarity goes a long way.</strong>
          <p>Build better money habits, one transaction at a time.</p>
        </div>
        <div className="profile">
          <div className="avatar">{user.name.slice(0, 1)}</div>
          <div>
            {user.name}
            <small>Private workspace</small>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void logout()}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <div className="eyebrow">YOUR MONEY, IN FOCUS</div>
            <h1>
              {tab === "Overview" ? "A clearer picture of your finances." : tab}
            </h1>
            <p>Track what comes in, understand what goes out.</p>
          </div>
          <label className="month">
            Reporting month
            <input
              aria-label="Reporting month"
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              required
            />
          </label>
        </header>
        <div className="demo-banner">
          <span>◉</span> Your private workspace · PHP accounts
        </div>
        <button
          className="mobile-logout text-button"
          disabled={busy}
          onClick={() => void logout()}
        >
          Sign out · {user.name}
        </button>
        {error && (
          <div role="alert" className="error">
            {error}
            <button onClick={() => void reload()} disabled={busy}>
              Retry connection
            </button>
          </div>
        )}
        {notice && (
          <div role="status" className="notice">
            {notice}
          </div>
        )}
        {loading && <p role="status">Loading your workspace…</p>}
        {tab === "Overview" && (
          <>
            <section className="stats" aria-label="Monthly totals">
              {[
                ["Total balance", total, "Across your accounts"],
                ["Income", summary?.income_minor || 0, "This reporting month"],
                [
                  "Expenses",
                  summary?.expense_minor || 0,
                  "This reporting month",
                ],
                [
                  "Net cash flow",
                  summary?.net_minor || 0,
                  "Income minus expenses",
                ],
              ].map(([label, amount, hint], i) => (
                <article className={"stat stat-" + i} key={String(label)}>
                  <div>
                    {label}
                    <span>{["▤", "↙", "↗", "⇄"][i]}</span>
                  </div>
                  <strong>{summary ? money(Number(amount)) : "—"}</strong>
                  <small>{hint}</small>
                </article>
              ))}
            </section>
            <div className="grid">
              <section className="card">
                <div className="card-head">
                  <div>
                    <h2>Where your money goes</h2>
                    <p>Expenses by category</p>
                  </div>
                  <span className="pill">PHP</span>
                </div>
                {expenseCategories.length ? (
                  <div className="spending">
                    {expenseCategories.map(([c, n], i) => (
                      <div key={c} className="category">
                        <div>
                          <span>
                            <i
                              style={{
                                background: [
                                  "#176b56",
                                  "#83b6a6",
                                  "#c3d5ab",
                                  "#e9b86b",
                                ][i % 4],
                              }}
                            />
                            {c}
                          </span>
                          <strong>{money(n)}</strong>
                        </div>
                        <div className="bar">
                          <span
                            style={{
                              width: `${(n / (summary?.expense_minor || 1)) * 100}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty">
                    <span>◎</span>
                    <h3>Your story starts here</h3>
                    <p>Add an expense to see your spending breakdown.</p>
                    <button onClick={() => setTab("Transactions")}>
                      Add a transaction
                    </button>
                  </div>
                )}
              </section>
              <section className="card">
                <div className="card-head">
                  <div>
                    <h2>Your accounts</h2>
                    <p>Every peso has a place</p>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setTab("Accounts")}
                  >
                    Manage →
                  </button>
                </div>
                {accounts.length ? (
                  accounts.map((a) => (
                    <div className="account-row" key={a.id}>
                      <span className="account-icon">
                        {a.kind === "bank" ? "▤" : "◈"}
                      </span>
                      <div>
                        <strong>{a.name}</strong>
                        <small>{a.kind} · PHP</small>
                      </div>
                      <b>{money(a.balance_minor)}</b>
                    </div>
                  ))
                ) : (
                  <div className="empty">
                    <span>▤</span>
                    <h3>Make yourself at home</h3>
                    <p>Add your bank account, e-wallet, or cash wallet.</p>
                    <button onClick={() => setTab("Accounts")}>
                      Create an account
                    </button>
                  </div>
                )}
              </section>
            </div>
          </>
        )}
        {tab === "Accounts" && (
          <section className="card">
            <h2>Create an account</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const d = new FormData(form);
                void action(async () => {
                  await api(
                    "accounts",
                    json({ name: d.get("name"), kind: d.get("kind") }),
                  );
                  form.reset();
                }, "Account created.");
              }}
            >
              <label>
                Account name
                <input
                  name="name"
                  placeholder="e.g. Everyday wallet"
                  required
                  maxLength={80}
                />
              </label>
              <label>
                Account type
                <select name="kind">
                  <option value="cash">Cash</option>
                  <option value="bank">Bank</option>
                  <option value="ewallet">E-wallet</option>
                </select>
              </label>
              <button disabled={busy}>Create account</button>
            </form>
            {accounts.map((a) => (
              <form
                key={`${a.id}-${a.version}`}
                onSubmit={(e) => {
                  e.preventDefault();
                  const d = new FormData(e.currentTarget);
                  void action(
                    () =>
                      api(`accounts/${a.id}`, {
                        ...json({
                          name: d.get("name"),
                          kind: d.get("kind"),
                          opening_minor: a.opening_minor,
                          archived: a.archived,
                          version: a.version,
                        }),
                        method: "PATCH",
                      }),
                    "Account updated.",
                  );
                }}
              >
                <label>
                  Account name
                  <input
                    name="name"
                    defaultValue={a.name}
                    required
                    maxLength={80}
                  />
                </label>
                <label>
                  Type
                  <select name="kind" defaultValue={a.kind}>
                    <option value="cash">Cash</option>
                    <option value="bank">Bank</option>
                    <option value="ewallet">E-wallet</option>
                  </select>
                </label>
                <span>
                  {money(a.balance_minor)} {a.archived && "(Archived)"}
                </span>
                <button disabled={busy}>Save changes</button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void action(
                      () =>
                        api(`accounts/${a.id}`, {
                          ...json({
                            name: a.name,
                            kind: a.kind,
                            opening_minor: a.opening_minor,
                            archived: !a.archived,
                            version: a.version,
                          }),
                          method: "PATCH",
                        }),
                      a.archived
                        ? "Account restored."
                        : "Account archived. History preserved.",
                    )
                  }
                >
                  {a.archived ? "Restore" : "Archive"}
                </button>
              </form>
            ))}
          </section>
        )}
        {tab === "Transactions" && (
          <section className="card">
            <h2>{editing ? "Edit transaction" : "Add a transaction"}</h2>
            <form
              key={editing?.id ?? "new"}
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const d = new FormData(form);
                void action(async () => {
                  await api(
                    editing ? `transactions/${editing.id}` : "transactions",
                    {
                      ...json({
                        ...(editing ? { version: editing.version } : {}),
                        account_id: Number(d.get("account_id")),
                        occurred_at: d.get("date"),
                        description: d.get("description"),
                        category: d.get("category"),
                        kind: d.get("kind"),
                        amount: d.get("amount"),
                      }),
                      method: editing ? "PATCH" : "POST",
                    },
                  );
                  setEditing(null);
                  form.reset();
                }, "Transaction saved.");
              }}
            >
              {editing ? (
                <label>
                  Account
                  <select
                    name="account_id"
                    defaultValue={editing.account_id}
                    required
                  >
                    {activeAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                accountSelect
              )}
              <label>
                Date
                <input
                  type="date"
                  name="date"
                  defaultValue={editing?.occurred_at}
                  required
                />
              </label>
              <label>
                Description
                <input
                  name="description"
                  defaultValue={editing?.description}
                  required
                  maxLength={160}
                  placeholder="e.g. Weekly groceries"
                />
              </label>
              <label>
                Category
                <select name="category" defaultValue={editing?.category}>
                  {categories.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label>
                Type
                <select name="kind" defaultValue={editing?.kind}>
                  <option value="expense">Expense</option>
                  <option value="income">Income</option>
                </select>
              </label>
              <label>
                Amount (PHP)
                <input
                  name="amount"
                  defaultValue={
                    editing
                      ? (editing.amount_minor / 100).toFixed(2)
                      : undefined
                  }
                  type="number"
                  min="0.01"
                  max="1000000000"
                  step="0.01"
                  required
                />
              </label>
              <button disabled={busy || !activeAccounts.length}>
                {editing ? "Save changes" : "Save transaction"}
              </button>
              {editing && (
                <button type="button" onClick={() => setEditing(null)}>
                  Cancel edit
                </button>
              )}
            </form>
          </section>
        )}
        {(tab === "Overview" || tab === "Transactions") && (
          <section className="card transactions">
            <div className="card-head">
              <div>
                <h2>Recent transactions</h2>
                <p>
                  Entries across all months; load more to view older history
                </p>
              </div>
              {tab === "Overview" && (
                <button
                  className="text-button"
                  onClick={() => setTab("Transactions")}
                >
                  Add new +
                </button>
              )}
            </div>
            {transactions.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Description</th>
                      <th>Category</th>
                      <th>Date</th>
                      <th>Amount</th>
                      {tab === "Transactions" && <th>Action</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((t) => (
                      <tr key={t.id}>
                        <td>
                          <strong>{t.description}</strong>
                          <small>
                            {accounts.find((a) => a.id === t.account_id)?.name}
                          </small>
                        </td>
                        <td>
                          <span className="pill">{t.category}</span>
                        </td>
                        <td>{t.occurred_at}</td>
                        <td className={t.kind === "income" ? "positive" : ""}>
                          {t.kind === "income" ? "+" : "−"}
                          {money(t.amount_minor)}
                        </td>
                        {tab === "Transactions" && (
                          <td>
                            <button
                              className="text-button"
                              disabled={
                                busy ||
                                accounts.some(
                                  (a) => a.id === t.account_id && a.archived,
                                )
                              }
                              onClick={() => setEditing(t)}
                            >
                              Edit
                            </button>
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() => {
                                if (window.confirm("Delete this transaction?"))
                                  void action(
                                    () =>
                                      api(`transactions/${t.id}`, {
                                        method: "DELETE",
                                      }),
                                    "Transaction deleted.",
                                  );
                              }}
                            >
                              Delete
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty compact">
                <p>
                  No transactions yet. Add your first entry or import a CSV.
                </p>
              </div>
            )}
          </section>
        )}
        {tab === "Transactions" && hasMore && (
          <button disabled={busy || loading} onClick={() => void loadMore()}>
            Load older transactions
          </button>
        )}
        {tab === "Budgets" && (
          <section className="card">
            <h2>Monthly budgets</h2>
            <p>Set a spending limit for {month}.</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const d = new FormData(e.currentTarget);
                void action(
                  () =>
                    api(
                      "budgets",
                      json({
                        month,
                        category: d.get("category"),
                        amount: d.get("amount"),
                      }),
                    ),
                  "Budget saved.",
                );
              }}
            >
              <label>
                Category
                <select name="category">
                  {categories
                    .filter((c) => c !== "Income")
                    .map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                </select>
              </label>
              <label>
                Limit (PHP)
                <input
                  name="amount"
                  type="number"
                  min="0.01"
                  max="1000000000"
                  step="0.01"
                  required
                />
              </label>
              <button disabled={busy}>Save budget</button>
            </form>
            {summary?.budgets.map((b) => (
              <div className="category" key={b.id}>
                <div>
                  <strong>{b.category}</strong>
                  <span>
                    {money(b.spent_minor)} / {money(b.limit_minor)}
                  </span>
                </div>
                <progress
                  max={b.limit_minor}
                  value={Math.min(b.spent_minor, b.limit_minor)}
                />
                <p>
                  {b.spent_minor > b.limit_minor
                    ? `${money(b.spent_minor - b.limit_minor)} over budget`
                    : `${money(b.limit_minor - b.spent_minor)} remaining`}
                </p>
              </div>
            ))}
            {!summary?.budgets.length && <p>No budgets for this month yet.</p>}
          </section>
        )}
        {tab === "CSV import" && (
          <section className="card">
            <h2>Import your transactions</h2>
            <p>
              UTF-8 CSV · up to 1 MB / 5,000 rows. Preview before adding any
              entries.
            </p>
            <p>
              <a href="/sample-transactions.csv" download>
                Download a synthetic example ↗
              </a>
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!file) return;
                void action(async () => {
                  const d = new FormData();
                  d.append("account_id", importAccount);
                  d.append("file", file);
                  setPreview(
                    await api("imports/preview", { method: "POST", body: d }),
                  );
                  setAck(false);
                }, "Preview ready. Review before confirming.");
              }}
            >
              <label>
                Account
                <select
                  required
                  value={importAccount}
                  onChange={(e) => {
                    setImportAccount(e.target.value);
                    setPreview(null);
                  }}
                >
                  <option value="">Select an account</option>
                  {activeAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                CSV file
                <input
                  type="file"
                  accept=".csv,text/csv"
                  required
                  onChange={(e) => {
                    setFile(e.target.files?.[0] || null);
                    setPreview(null);
                  }}
                />
              </label>
              <button disabled={busy || !activeAccounts.length}>
                Preview import
              </button>
            </form>
            {preview && (
              <div>
                <h3>
                  {preview.count} transactions · {preview.duplicate_candidates}{" "}
                  duplicate candidates
                </h3>
                <p>
                  Preview shows the first 20 rows. Same date and amount may
                  represent legitimate purchases; all rows are preserved.
                </p>
                {preview.already_imported ? (
                  <p role="alert">
                    This exact file has already been imported into this account.
                  </p>
                ) : (
                  <>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Description</th>
                            <th>Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.rows.map((r, i) => (
                            <tr key={i}>
                              <td>{r.occurred_at}</td>
                              <td>{r.description}</td>
                              <td>{money(r.amount_minor)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={ack}
                        onChange={(e) => setAck(e.target.checked)}
                      />
                      I reviewed the preview and want to import all rows,
                      including duplicate candidates.
                    </label>
                    <button
                      disabled={!ack || busy}
                      onClick={() =>
                        void action(async () => {
                          const d = new FormData();
                          d.append("account_id", importAccount);
                          d.append("file", file!);
                          d.append("digest", preview.digest);
                          d.append("acknowledge_duplicates", "true");
                          await api("imports/confirm", {
                            method: "POST",
                            body: d,
                          });
                          setPreview(null);
                        }, "Import complete.")
                      }
                    >
                      Confirm import
                    </button>
                  </>
                )}
              </div>
            )}
          </section>
        )}
        <footer>
          PesoPilot{" "}
          <span>Built for a little more financial peace of mind.</span>
          <small>Local development · Not connected to your bank</small>
        </footer>
      </main>
    </div>
  );
}
