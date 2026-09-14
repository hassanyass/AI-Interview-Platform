import React, { createContext, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
import { adminClient } from "../api/adminClient";

type Role = "admin" | "candidate" | "unknown";

interface RoleContextType {
  role: Role;
  isLoadingRole: boolean;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

export const RoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading: isAuthLoading } = useAuth();
  const [role, setRole] = useState<Role>("unknown");
  const [isLoadingRole, setIsLoadingRole] = useState<boolean>(true);

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
        await adminClient.ping();
        if (mounted) {
          setRole("admin");
        }
      } catch (err) {
        if (mounted) {
          setRole("candidate");
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
  }, [user, isAuthLoading]);

  return (
    <RoleContext.Provider value={{ role, isLoadingRole }}>
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
