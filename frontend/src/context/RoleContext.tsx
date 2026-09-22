import React, { createContext, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { adminClient } from "../api/adminClient";
import { isApiError } from "../lib/api";

type Role = "admin" | "candidate" | "unknown";

interface RoleContextType {
  role: Role;
  isLoadingRole: boolean;
  /** H2-E: set when the role could not be determined (network/timeout/5xx) -- not a "candidate" answer. */
  roleError: string | null;
  retryRoleCheck: () => void;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

export const RoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading: isAuthLoading } = useAuth();
  const [role, setRole] = useState<Role>("unknown");
  const [isLoadingRole, setIsLoadingRole] = useState<boolean>(true);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let mounted = true;

    async function checkRole() {
      if (isAuthLoading) return;

      if (!user) {
        if (mounted) {
          setRole("unknown");
          setIsLoadingRole(false);
        }
        return;
      }

      try {
        setRoleError(null);
        await adminClient.ping();
        if (mounted) {
          setRole("admin");
        }
      } catch (err) {
        if (!mounted) return;
        // H2-E: only a definite "not an admin" answer (401/403) means
        // candidate. A network blip, timeout or 5xx used to be mapped to
        // "candidate" too, which made AdminLayout sign the admin out.
        if (isApiError(err) && (err.status === 401 || err.status === 403)) {
          setRole("candidate");
        } else {
          setRole("unknown");
          setRoleError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (mounted) {
          setIsLoadingRole(false);
        }
      }
    }

    setIsLoadingRole(true);
    checkRole();

    return () => {
      mounted = false;
    };
  }, [user, isAuthLoading, attempt]);

  const retryRoleCheck = () => setAttempt((n) => n + 1);

  return (
    <RoleContext.Provider value={{ role, isLoadingRole, roleError, retryRoleCheck }}>
      {children}
    </RoleContext.Provider>
  );
};

export const useRole = () => {
  const context = useContext(RoleContext);
  if (context === undefined) {
    throw new Error("useRole must be used within a RoleProvider");
  }
  return context;
};
