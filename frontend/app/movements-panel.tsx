"use client";
import { useEffect, useRef, useState } from "react";
type Account = { id: number; name: string; archived: boolean };
type Expense = {
  id: number;
  description: string;
  occurred_at: string;
  kind: string;
  amount_minor: number;
};
type Movement = {
  id: number;
  occurred_at: string;
  amount_minor: number;
  source_id?: number;
  target_id?: number;
  original_id?: number;
};
type Props = {
  accounts: Account[];
  expenses: Expense[];
  request: (path: string, init?: RequestInit) => Promise<unknown>;
  onSaved: () => Promise<void>;
};
const money = (value: number) =>
  new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(
    value / 100,
  );

export default function MovementsPanel({
  accounts,
  expenses,
  request,
  onSaved,
}: Props) {
  const transferKey = useRef("");
  const refundKey = useRef("");
  const [rows, setRows] = useState<Movement[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const active = accounts.filter((account) => !account.archived);
  useEffect(() => {
    let alive = true;
    Promise.all([request("transfers"), request("refunds")])
      .then((values) => {
        if (alive) setRows(values.flat() as Movement[]);
      })
      .catch((e) => {
        if (alive) setError((e as Error).message);
      });
    return () => {
      alive = false;
    };
  }, [request]);
  async function save(
    event: React.FormEvent<HTMLFormElement>,
    refund: boolean,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const key = refund ? refundKey : transferKey;
    key.current ||= crypto.randomUUID();
    setBusy(true);
    setError("");
    setNotice("");
    const body = {
      occurred_at: values.get("date"),
      amount: values.get("amount"),
      idempotency_key: key.current,
      ...(refund
        ? {}
        : {
            source_id: Number(values.get("source")),
            target_id: Number(values.get("target")),
          }),
    };
    try {
      await request(
        refund ? `transactions/${values.get("original")}/refunds` : "transfers",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      key.current = "";
      form.reset();
      setNotice(refund ? "Refund recorded." : "Transfer recorded.");
      setRows(
        (
          await Promise.all([request("transfers"), request("refunds")])
        ).flat() as Movement[],
      );
      await onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>Transfers and refunds</h2>
      <p>
        Transfers move balances between your PHP accounts and are excluded from
        income and expenses. Refunds credit the original account and reduce
        expenses in the refund month.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <h3>Transfer between accounts</h3>
      <form onSubmit={(event) => void save(event, false)}>
        <label>
          Source account
          <select name="source" required defaultValue="">
            <option value="" disabled>
              Select source
            </option>
            {active.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Target account
          <select name="target" required defaultValue="">
            <option value="" disabled>
              Select target
            </option>
            {active.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Transfer date
          <input name="date" type="date" required />
        </label>
        <label>
          Transfer amount (PHP)
          <input
            name="amount"
            type="number"
            min="0.01"
            max="1000000000"
            step="0.01"
            required
          />
        </label>
        <button disabled={busy || active.length < 2}>Record transfer</button>
        <button
          type="button"
          disabled={busy}
          onClick={(event) => {
            if (
              window.confirm(
                "Check movement history before starting a new transfer after a connection error. Start a new draft?",
              )
            ) {
              transferKey.current = "";
              event.currentTarget.form?.reset();
            }
          }}
        >
          New transfer draft
        </button>
      </form>
      <h3>Refund an expense</h3>
      <form onSubmit={(event) => void save(event, true)}>
        <label>
          Original expense
          <select name="original" required defaultValue="">
            <option value="" disabled>
              Select loaded expense
            </option>
            {expenses
              .filter((expense) => expense.kind === "expense")
              .map((expense) => (
                <option key={expense.id} value={expense.id}>
                  {expense.description} · {expense.occurred_at} ·{" "}
                  {money(expense.amount_minor)}
                </option>
              ))}
          </select>
        </label>
        <label>
          Refund date
          <input name="date" type="date" required />
        </label>
        <label>
          Refund amount (PHP)
          <input
            name="amount"
            type="number"
            min="0.01"
            max="1000000000"
            step="0.01"
            required
          />
        </label>
        <button disabled={busy}>Record refund</button>
      </form>
      <p>
        Entries preserve their original financial values. After a connection
        error, retry the unchanged form and check history before starting a new
        draft. Manual accounts can have overdraft balances. History shows the
        latest 500 movements of each type.
      </p>
      {rows.map((row) => (
        <div
          className="account-row"
          key={`${row.original_id ? "refund" : "transfer"}-${row.id}`}
        >
          <strong>{row.original_id ? "Refund" : "Transfer"}</strong>
          <span>{row.occurred_at}</span>
          <b>{money(row.amount_minor)}</b>
        </div>
      ))}
    </section>
  );
}
