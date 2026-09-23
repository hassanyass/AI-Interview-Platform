// @vitest-environment jsdom
/**
 * H4-B: the one table the admin screens share (responsive plan R0).
 *
 * Both renderings are in the DOM at once and Tailwind's `hidden md:block`
 * / `md:hidden` decide which is visible, so jsdom can assert both without
 * a viewport. What matters is that the card rendering never drops a
 * column silently -- R3's finding was that the actions column was the one
 * scrolled off-screen on a phone, and this component exists to fix that.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";

import { ResponsiveTable, type ResponsiveColumn } from "./ResponsiveTable";

interface Candidate {
  id: string;
  name: string;
  score: string;
  internal: string;
}

const rows: Candidate[] = [
  { id: "1", name: "Ada", score: "82", internal: "hidden-1" },
  { id: "2", name: "Grace", score: "91", internal: "hidden-2" },
];

const columns: ResponsiveColumn<Candidate>[] = [
  { key: "name", header: "Candidate", cell: (r) => r.name, primary: true },
  { key: "score", header: "Score", cell: (r) => r.score },
  { key: "internal", header: "Internal", cell: (r) => r.internal, hideOnCard: true },
  { key: "actions", header: "", cell: (r) => <button>Open {r.name}</button>, actions: true },
];

const renderTable = (props: Partial<React.ComponentProps<typeof ResponsiveTable<Candidate>>> = {}) =>
  render(<ResponsiveTable columns={columns} rows={rows} rowKey={(r) => r.id} {...props} />);

describe("ResponsiveTable", () => {
  afterEach(() => cleanup());

  it("renders a real table with every column, header and row", () => {
    renderTable();
    const table = screen.getByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual(["Candidate", "Score", "Internal", ""]);
    // header row + one row per candidate
    expect(within(table).getAllByRole("row")).toHaveLength(rows.length + 1);
    expect(within(table).getByText("hidden-1")).toBeTruthy();
  });

  it("renders one card per row with the primary column as its title", () => {
    renderTable();
    const cards = screen.getAllByRole("listitem");
    expect(cards).toHaveLength(rows.length);
    expect(cards[0].textContent).toContain("Ada");
    expect(cards[1].textContent).toContain("Grace");
  });

  it("labels each card field and keeps the actions, but drops hideOnCard columns", () => {
    renderTable();
    const card = screen.getAllByRole("listitem")[0];
    expect(within(card).getByText("Score")).toBeTruthy();      // the <dt> label
    expect(within(card).getByText("82")).toBeTruthy();
    expect(within(card).getByRole("button", { name: "Open Ada" })).toBeTruthy();
    expect(within(card).queryByText("hidden-1")).toBeNull();   // hideOnCard
    expect(within(card).queryByText("Internal")).toBeNull();
  });

  it("puts the actions last in the card, so they are never what scrolls away", () => {
    renderTable();
    const card = screen.getAllByRole("listitem")[0];
    const button = within(card).getByRole("button", { name: "Open Ada" });
    expect(card.lastElementChild?.contains(button)).toBe(true);
  });

  it("shows the empty state instead of either rendering when there are no rows", () => {
    render(
      <ResponsiveTable
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        empty={<p>No candidates yet</p>}
      />
    );
    expect(screen.getByText("No candidates yet")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("still renders an empty table when no empty state was supplied", () => {
    render(<ResponsiveTable columns={columns} rows={[]} rowKey={(r) => r.id} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(1);   // the header only
  });

  it("uses the caption for both renderings' accessible names", () => {
    renderTable({ caption: "Candidates for this job" });
    expect(screen.getByRole("table", { name: "Candidates for this job" })).toBeTruthy();
    expect(screen.getByRole("list", { name: "Candidates for this job" })).toBeTruthy();
  });
});
