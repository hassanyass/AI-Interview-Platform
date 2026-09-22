import * as React from "react";
import { cn } from "./utils";

/**
 * Responsive plan R0 (docs/responsive-design-plan.md §3): one table, two
 * renderings. At `md` and above it is a plain <table> (the existing admin
 * tables' look: uppercase muted header, divided rows). Below `md` each row
 * becomes a card -- the `primary` column as the card's title, every other
 * column as a "label: value" line, and `actions` pinned at the end -- so
 * the action column is never the one scrolled off-screen (R3's finding on
 * JobResultsPage). Both renderings are in the DOM; Tailwind's `hidden
 * md:block` / `md:hidden` pick one, so no JS breakpoint is needed.
 *
 * Cell content is whatever the caller renders (Badges, links, buttons);
 * this component only owns the structure.
 */
export interface ResponsiveColumn<Row> {
  key: string;
  header: React.ReactNode;
  cell: (row: Row) => React.ReactNode;
  /** The card's title below `md`. Exactly one column should set this. */
  primary?: boolean;
  /** Rendered as the card's action row below `md`; right-aligned (end) in the table. */
  actions?: boolean;
  /** Skip this column in the card rendering (e.g. purely decorative). */
  hideOnCard?: boolean;
  /** Extra classes for the <th>/<td> (widths, alignment). */
  className?: string;
}

export interface ResponsiveTableProps<Row> {
  columns: ResponsiveColumn<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  /** Shown instead of the table/cards when `rows` is empty. */
  empty?: React.ReactNode;
  /** Optional accessible description of the table. */
  caption?: string;
  className?: string;
}

export function ResponsiveTable<Row>({ columns, rows, rowKey, empty, caption, className }: ResponsiveTableProps<Row>) {
  if (rows.length === 0 && empty !== undefined) {
    return <>{empty}</>;
  }
  const primary = columns.find((c) => c.primary);
  const actions = columns.find((c) => c.actions);
  const cardFields = columns.filter((c) => !c.primary && !c.actions && !c.hideOnCard);

  return (
    <div className={className}>
      {/* >= md: the table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm text-start">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead className="border-b border-border bg-muted/20 text-xs uppercase text-muted-foreground">
            <tr>
              {columns.map((col) => (
                <th key={col.key} scope="col" className={cn("px-4 py-3 text-start font-semibold", col.actions && "text-end", col.className)}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => (
              <tr key={rowKey(row)} className="transition-colors hover:bg-muted/10">
                {columns.map((col) => (
                  <td key={col.key} className={cn("px-4 py-3 align-middle", col.actions && "text-end", col.className)}>
                    {col.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* < md: cards */}
      <ul className="divide-y divide-border md:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={rowKey(row)} className="flex flex-col gap-2 px-4 py-3">
            {primary && <div className="text-sm font-medium text-foreground">{primary.cell(row)}</div>}
            {cardFields.length > 0 && (
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
                {cardFields.map((col) => (
                  <React.Fragment key={col.key}>
                    <dt className="text-xs font-medium uppercase text-muted-foreground">{col.header}</dt>
                    <dd className="min-w-0">{col.cell(row)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            )}
            {actions && <div className="flex flex-wrap items-center gap-2 pt-1">{actions.cell(row)}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}
