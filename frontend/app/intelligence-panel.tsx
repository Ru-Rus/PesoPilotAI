"use client";
import { useEffect, useState } from "react";

type Fact = {
  id: string;
  title: string;
  kind: string;
  amount_minor: number;
  baseline_minor: number | null;
  category: string | null;
  source_description: string | null;
  explanation: string;
};
type Result = {
  income_minor: number;
  expense_minor: number;
  net_minor: number;
  facts: Fact[];
  limitations: string;
  warning?: string;
};
type Request = (path: string, init?: RequestInit) => Promise<unknown>;
const money = (value: number) =>
  new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(
    value / 100,
  );

export default function IntelligencePanel({
  request,
  month,
}: {
  request: Request;
  month: string;
}) {
  const [result, setResult] = useState<Result | null>(null);
  const [answer, setAnswer] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    let active = true;
    request(`ai/insights?month=${month}`)
      .then((value) => {
        if (active) {
          setResult(value as Result);
          setAnswer(null);
          setError("");
        }
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
  }, [request, month]);
  async function ask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      setAnswer(
        (await request("ai/questions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            month,
            question: data.get("question"),
            use_model: data.get("use_model") === "on",
          }),
        })) as Result,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const display = answer || result;
  return (
    <section className="card">
      <h2>Financial intelligence</h2>
      <p>
        Local statistical analysis of your recorded transactions. Every figure
        comes from verified backend calculations.
      </p>
      {busy && <p role="status">Calculating your insights…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={(event) => void ask(event)}>
        <label>
          Ask PesoPilot
          <input
            name="question"
            required
            maxLength={500}
            placeholder="How much did I spend?"
          />
        </label>
        <label className="check">
          <input name="use_model" type="checkbox" />
          Use configured local model (requires consent in Privacy)
        </label>
        <button disabled={busy}>Ask</button>
      </form>
      {display && (
        <div aria-live="polite">
          <p>
            Income: {money(display.income_minor)} · Expenses:{" "}
            {money(display.expense_minor)} · Net flow:{" "}
            {money(display.net_minor)}
          </p>
          {display.warning && <p role="status">{display.warning}</p>}
          {display.facts.map((fact) => (
            <article key={fact.id} className="category">
              <h3>
                {fact.title}
                {fact.category ? ` · ${fact.category}` : ""}
              </h3>
              <strong>{money(fact.amount_minor)}</strong>
              {fact.baseline_minor !== null && (
                <p>Baseline: {money(fact.baseline_minor)}</p>
              )}
              {fact.source_description && (
                <p>Saved description: {fact.source_description}</p>
              )}
              <p>{fact.explanation}</p>
            </article>
          ))}
          {!display.facts.length && (
            <p>No matching patterns in the recorded history.</p>
          )}
          <p>{display.limitations}</p>
        </div>
      )}
    </section>
  );
}

export function CategorySuggestion({ request }: { request: Request }) {
  const [result, setResult] = useState<{
    category: string | null;
    confidence: number;
    reason: string;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function suggest(button: HTMLButtonElement) {
    const description = button.form
      ? new FormData(button.form).get("description")
      : "";
    if (!description) {
      setError("Enter a description first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setResult(
        (await request("ai/categorize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description }),
        })) as typeof result,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button
        type="button"
        disabled={busy}
        onClick={(event) => void suggest(event.currentTarget)}
      >
        Suggest category
      </button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <div role="status">
          <p>
            {result.category || "No confident suggestion"} · Evidence score{" "}
            {(result.confidence * 100).toFixed(0)}%
          </p>
          <p>{result.reason}</p>
          {result.category && (
            <button
              type="button"
              onClick={(event) => {
                const select =
                  event.currentTarget.form?.elements.namedItem("category");
                if (select instanceof HTMLSelectElement)
                  select.value = result.category!;
              }}
            >
              Use suggestion
            </button>
          )}
        </div>
      )}
    </div>
  );
}
