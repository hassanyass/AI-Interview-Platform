// @vitest-environment jsdom
/**
 * H2-E: only a definite 401/403 from /admin/ping means "candidate". A
 * network failure, timeout or 5xx leaves the role unknown with an error
 * (AdminLayout then offers a retry instead of signing the admin out).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";

vi.mock("./AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1" }, isLoading: false }),
}));
const ping = vi.fn();
vi.mock("../api/adminClient", () => ({ adminClient: { ping: () => ping() } }));

const { RoleProvider, useRole } = await import("./RoleContext");
const { ApiError } = await import("../lib/api");

function Probe() {
  const { role, isLoadingRole, roleError, retryRoleCheck } = useRole();
  return (
    <div>
      <span data-testid="role">{isLoadingRole ? "loading" : role}</span>
      <span data-testid="err">{roleError ?? ""}</span>
      <button onClick={retryRoleCheck}>retry</button>
    </div>
  );
}

describe("RoleContext", () => {
  afterEach(() => cleanup());

  it("admin when ping succeeds", async () => {
    ping.mockResolvedValueOnce({ status: "ok" });
    render(<RoleProvider><Probe /></RoleProvider>);
    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("admin"));
  });

  it("candidate on a definite 401/403", async () => {
    ping.mockRejectedValueOnce(new ApiError("Forbidden", { status: 403 }));
    render(<RoleProvider><Probe /></RoleProvider>);
    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("candidate"));
    expect(screen.getByTestId("err").textContent).toBe("");
  });

  it("unknown + error on a network failure, and retry re-checks", async () => {
    ping.mockRejectedValueOnce(new ApiError("Could not reach the server.", { status: 0, code: "network" }));
    render(<RoleProvider><Probe /></RoleProvider>);
    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("unknown"));
    expect(screen.getByTestId("err").textContent).toBe("Could not reach the server.");
    ping.mockResolvedValueOnce({ status: "ok" });
    await act(async () => { screen.getByText("retry").click(); });
    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("admin"));
    expect(screen.getByTestId("err").textContent).toBe("");
  });

  it("unknown + error on a 5xx too", async () => {
    ping.mockRejectedValueOnce(new ApiError("Internal server error", { status: 500 }));
    render(<RoleProvider><Probe /></RoleProvider>);
    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("unknown"));
  });
});
