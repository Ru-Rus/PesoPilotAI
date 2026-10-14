import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Dashboard from "../app/page";
import IntelligencePanel, {
  CategorySuggestion,
} from "../app/intelligence-panel";
import PrivacyPanel from "../app/privacy-panel";
import SessionPanel from "../app/session-panel";
import MovementsPanel from "../app/movements-panel";

const account = {
  id: 1,
  name: "Wallet",
  kind: "cash",
  balance_minor: 100,
  opening_minor: 0,
  version: 1,
  archived: false,
};
const transaction = {
  id: 2,
  account_id: 1,
  occurred_at: "2026-10-01",
  description: "Coffee",
  category: "Other",
  kind: "expense",
  amount_minor: 3,
  version: 1,
};
const summary = {
  income_minor: 0,
  expense_minor: 3,
  net_minor: -3,
  categories: { Other: 3 },
  budgets: [],
};
function mockAPI(
  options: {
    anonymous?: boolean;
    conflict?: boolean;
    many?: boolean;
    failed?: boolean;
    withBudget?: boolean;
  } = {},
) {
  const request = vi.fn(async (input: string, init?: RequestInit) => {
    const path = input.replace("/api/v1/", "");
    if (options.anonymous)
      return new Response(JSON.stringify({ detail: "Sign in to continue" }), {
        status: 401,
      });
    if (options.failed)
      return new Response(JSON.stringify({ detail: "Database unavailable" }), {
        status: 503,
      });
    if (init?.method === "PATCH" && options.conflict)
      return new Response(JSON.stringify({ detail: "Account changed" }), {
        status: 409,
      });
    let value: unknown = {};
    if (path === "auth/me")
      value = { id: "alice", name: "Alice", csrf_token: "test-only-csrf" };
    else if (path === "accounts") value = [account];
    else if (path.startsWith("transactions?") && !path.includes("before_id"))
      value = options.many
        ? Array.from({ length: 100 }, (_, i) => ({
            ...transaction,
            id: 101 - i,
          }))
        : [transaction];
    else if (path.includes("before_id"))
      value = [{ ...transaction, id: 1, description: "Older" }];
    else if (path.startsWith("analytics"))
      value = options.withBudget
        ? {
            ...summary,
            budgets: [
              {
                id: 9,
                category: "Other",
                limit_minor: 99,
                spent_minor: 3,
                version: 99,
              },
            ],
          }
        : summary;
    return new Response(JSON.stringify(value), { status: 200 });
  });
  vi.stubGlobal("fetch", request);
  return request;
}

describe("Dashboard regression journeys", () => {
  it("shows loading while session lookup is unresolved", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(<Dashboard />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking your session",
    );
  });
  it("shows provider login for anonymous sessions", async () => {
    mockAPI({ anonymous: true });
    render(<Dashboard />);
    expect(
      await screen.findByRole("link", { name: /Sign in with Keycloak/ }),
    ).toHaveAttribute("href", "/api/v1/auth/login");
  });
  it("shows a private backend error without financial state", async () => {
    mockAPI({ failed: true });
    render(<Dashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Database unavailable",
    );
  });
  it("validates required transaction amount and description fields", async () => {
    mockAPI();
    render(<Dashboard />);
    await screen.findByText("Alice");
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    const amount = screen.getByLabelText("Amount (PHP)") as HTMLInputElement;
    expect(amount.checkValidity()).toBe(false);
    fireEvent.change(amount, { target: { value: "-1" } });
    expect(amount.checkValidity()).toBe(false);
    fireEvent.change(amount, { target: { value: "0.01" } });
    expect(amount.checkValidity()).toBe(true);
    expect(
      (screen.getByLabelText("Description") as HTMLInputElement).required,
    ).toBe(true);
  });
  it("reloads conflicts and cancels stale edits", async () => {
    const request = mockAPI({ conflict: true });
    render(<Dashboard />);
    await screen.findByText("Alice");
    fireEvent.click(screen.getByRole("button", { name: "Accounts" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Save changes" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Current values have been loaded",
    );
    expect(
      request.mock.calls.filter(([url]) => url.endsWith("auth/me")).length,
    ).toBeGreaterThan(1);
  });
  it("loads older history using the last date and ID", async () => {
    const request = mockAPI({ many: true });
    render(<Dashboard />);
    await screen.findByText("Alice");
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Load older transactions" }),
    );
    expect(await screen.findByText("Older")).toBeInTheDocument();
    expect(
      request.mock.calls.some(([url]) =>
        url.includes("before_date=2026-10-01&before_id=2"),
      ),
    ).toBe(true);
  });
});

describe("privacy, intelligence and sessions", () => {
  it("preserves movement idempotency keys across uncertain retries", async () => {
    let submissions = 0;
    const request = vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        submissions++;
        if (submissions === 1) throw new Error("Retry after network failure");
        return { id: 1 };
      }
      return [];
    });
    render(
      <MovementsPanel
        accounts={[account, { ...account, id: 3, name: "Savings" }]}
        expenses={[transaction]}
        request={request}
        onSaved={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    fireEvent.change(screen.getByLabelText("Source account"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Target account"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText("Transfer date"), {
      target: { value: "2026-10-01" },
    });
    fireEvent.change(screen.getByLabelText("Transfer amount (PHP)"), {
      target: { value: "0.01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record transfer" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Record transfer" }));
    await screen.findByText("Transfer recorded.");
    const bodies = request.mock.calls
      .filter(([, init]) => init?.method === "POST")
      .map(([, init]) => JSON.parse(String(init?.body)));
    expect(bodies[0].idempotency_key).toBe(bodies[1].idempotency_key);
    expect(bodies[1].source_id).toBe(1);
  });
  it("restores consent when the server rejects an optimistic toggle", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        enabled: false,
        version: 0,
        scope: "Local only",
      })
      .mockRejectedValueOnce(new Error("Consent changed"));
    render(
      <PrivacyPanel request={request} download={vi.fn()} onDeleted={vi.fn()} />,
    );
    fireEvent.click(
      await screen.findByLabelText("Allow local model processing"),
    );
    await screen.findByRole("alert");
    expect(
      screen.getByLabelText("Allow local model processing"),
    ).not.toBeChecked();
  });
  it("retains the transaction version when a budget has a different version", async () => {
    const request = mockAPI({ withBudget: true });
    render(<Dashboard />);
    await screen.findByText("Coffee");
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(
        request.mock.calls.some(([, init]) => init?.method === "PATCH"),
      ).toBe(true),
    );
    const payload = JSON.parse(
      String(
        request.mock.calls.find(([, init]) => init?.method === "PATCH")![1]
          ?.body,
      ),
    );
    expect(payload.version).toBe(transaction.version);
  });
  it("requires explicit category acceptance without writing a transaction", async () => {
    const request = vi.fn().mockResolvedValue({
      category: "Transport",
      confidence: 0.9,
      reason: "Relative evidence",
    });
    render(
      <form>
        <input name="description" defaultValue="Bus" />
        <select name="category" defaultValue="Other" aria-label="Category">
          <option>Other</option>
          <option>Transport</option>
        </select>
        <CategorySuggestion request={request} />
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Suggest category" }));
    await screen.findByText(/Transport · Evidence/);
    expect(screen.getByLabelText("Category")).toHaveValue("Other");
    fireEvent.click(screen.getByRole("button", { name: "Use suggestion" }));
    expect(screen.getByLabelText("Category")).toHaveValue("Transport");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("rejects empty categorization input locally", async () => {
    const request = vi.fn();
    render(
      <form>
        <input name="description" />
        <CategorySuggestion request={request} />
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Suggest category" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a description");
    expect(request).not.toHaveBeenCalled();
  });
  it("renders descriptions as text and shows verified assistant failures", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        ...summary,
        facts: [
          {
            id: "r",
            title: "Repeated",
            amount_minor: 3,
            baseline_minor: null,
            source_description: "<img src=x onerror=alert(1)>",
            explanation: "Recorded only",
          },
        ],
        limitations: "Recorded only",
      })
      .mockRejectedValueOnce(new Error("Unsupported topic"));
    const { container } = render(
      <IntelligencePanel request={request} month="2026-10" />,
    );
    await screen.findByText(/Saved description:/);
    expect(container.querySelector("img")).toBeNull();
    fireEvent.change(screen.getByLabelText("Ask PesoPilot"), {
      target: { value: "delete data" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unsupported topic",
    );
  });
  it("saves consent with versions and keeps deletion behind exact confirmation", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({
        enabled: false,
        version: 0,
        scope: "Local only",
      })
      .mockResolvedValueOnce({
        enabled: true,
        version: 1,
        scope: "Local only",
      });
    render(
      <PrivacyPanel request={request} download={vi.fn()} onDeleted={vi.fn()} />,
    );
    fireEvent.click(
      await screen.findByLabelText("Allow local model processing"),
    );
    await screen.findByText("Model preference saved.");
    expect(request.mock.calls[1][1].body).toContain('"version":0');
    fireEvent.change(screen.getByLabelText("Deletion confirmation"), {
      target: { value: "wrong" },
    });
    fireEvent.submit(
      screen.getByLabelText("Deletion confirmation").closest("form")!,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Type DELETE MY DATA exactly",
    );
    expect(request.mock.calls.some(([path]) => path === "me")).toBe(false);
  });
  it("revokes a session only after user confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const request = vi
      .fn()
      .mockResolvedValueOnce([
        {
          id: "hash",
          current: false,
          created_at: "2026-10-01T00:00:00Z",
          expires_at: "2026-10-01T08:00:00Z",
          last_seen_at: "2026-10-01T01:00:00Z",
        },
      ])
      .mockResolvedValueOnce(null);
    render(<SessionPanel request={request} onChange={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("auth/sessions/hash", {
        method: "DELETE",
      }),
    );
  });
});
