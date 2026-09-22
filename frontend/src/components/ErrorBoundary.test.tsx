// @vitest-environment jsdom
/**
 * H2-E: a throwing child renders the boundary's fallback instead of a
 * blank page; the interview variant uses the candidate-facing copy.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("react-i18next", () => ({
  withTranslation: () => (Component: any) => (props: any) => <Component {...props} t={(k: string) => k} />,
}));

const { ErrorBoundary } = await import("./ErrorBoundary");

function Boom(): never {
  throw new Error("render exploded");
}

describe("ErrorBoundary", () => {
  afterEach(() => cleanup());

  it("renders children when nothing throws", () => {
    render(<ErrorBoundary><p>fine</p></ErrorBoundary>);
    expect(screen.getByText("fine")).toBeTruthy();
  });

  it("shows the page fallback with a reload button when a child throws", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("errorBoundary.title")).toBeTruthy();
    expect(screen.getByText("errorBoundary.reload")).toBeTruthy();
    expect(screen.getByText(/render exploded/)).toBeTruthy();
  });

  it("uses the candidate copy for the interview variant", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary variant="interview"><Boom /></ErrorBoundary>);
    expect(screen.getByText("errorBoundary.interviewTitle")).toBeTruthy();
    expect(screen.getByText("errorBoundary.interviewBody")).toBeTruthy();
  });
});
