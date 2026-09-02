import { Navigate, Outlet, Link, useLocation } from "react-router-dom";
import { useRole } from "../../context/RoleContext";
import { useAuth } from "../../context/AuthContext";
import { Briefcase, Settings, LogOut } from "lucide-react";
import { LanguageToggle } from "../../components/ui/LanguageToggle";
import { useTranslation } from "react-i18next";

export default function AdminLayout() {
  const { t } = useTranslation();
  const { role, isLoadingRole } = useRole();
  const { signOut } = useAuth();
  const location = useLocation();

  if (isLoadingRole || role === "unknown") {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-foreground">
        {t('adminLayout.loading')}
      </div>
    );
  }

  if (role !== "admin") {
    // If a non-admin tries to access /admin, log them out and kick them to login
    // since the candidate self-serve dashboard no longer exists.
    signOut();
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen w-full bg-background text-foreground">
      {/* Sidebar */}
      <aside className="w-64 border-e border-secondary-foreground/10 bg-secondary text-secondary-foreground flex flex-col">
        <div className="h-24 px-6 flex flex-col justify-center border-b border-secondary-foreground/10 shrink-0">
          <div className="flex flex-col">
            <span className="text-xl font-bold tracking-tight text-white">
              <span dir="ltr" className="inline-block">e&</span> <span className="text-white/50 font-normal">|</span> هِمّة
            </span>
            <span className="text-xs text-white/70 mt-0.5">{t('adminLayout.adminPortal')}</span>
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <Link
            to="/admin/jobs"
            className={`flex items-center gap-3 px-3 py-2 rounded-md transition-colors ${
              location.pathname.startsWith("/admin/jobs")
                ? "bg-white/15 text-white"
                : "text-white/70 hover:bg-white/10 hover:text-white"
            }`}
          >
            <Briefcase className="h-5 w-5" />
            <span>{t('adminLayout.jobs')}</span>
          </Link>
          <Link
            to="/admin/settings"
            className={`flex items-center gap-3 px-3 py-2 rounded-md transition-colors ${
              location.pathname.startsWith("/admin/settings")
                ? "bg-white/15 text-white"
                : "text-white/70 hover:bg-white/10 hover:text-white"
            }`}
          >
            <Settings className="h-5 w-5" />
            <span>{t('adminLayout.settings')}</span>
          </Link>
        </nav>
        <div className="p-4 border-t border-secondary-foreground/10 space-y-2">
          <button
            onClick={() => signOut()}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-white/70 hover:bg-red-500/20 hover:text-white transition-colors"
          >
            <LogOut className="h-5 w-5" />
            <span>{t('adminLayout.signOut')}</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto bg-background flex flex-col">
        <header className="h-24 px-8 flex items-center justify-end border-b border-border bg-card shrink-0">
          <LanguageToggle />
        </header>
        <div className="p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
