import { useEffect, useState } from "react";
import { Navigate, Outlet, Link, useLocation } from "react-router-dom";
import { useRole } from "../../context/RoleContext";
import { useAuth } from "../../context/AuthContext";
import { Briefcase, Settings, LogOut, Menu } from "lucide-react";
import { LanguageToggle } from "../../components/ui/LanguageToggle";
import { Drawer } from "../../components/ui/Drawer";
import { useTranslation } from "react-i18next";

export default function AdminLayout() {
  const { t } = useTranslation();
  const { role, isLoadingRole } = useRole();
  const { signOut } = useAuth();

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
    <AdminShell onSignOut={() => signOut()}>
      <Outlet />
    </AdminShell>
  );
}

/** The sidebar's contents -- rendered persistently at lg+ and inside the
 *  Drawer below it (R1). One markup, two containers. */
function SidebarPanel({ onSignOut }: { onSignOut: () => void }) {
  const { t } = useTranslation();
  const location = useLocation();
  return (
    <>
      {/* Design pass (2026-09-03): a single soft, leaf-shaped curve as a
          quiet brand texture on the otherwise flat maroon panel -- per
          the e& guide's Section 6 ("simple geometric motifs, soft
          corners") and Section 7 ("avoid decoration for its own sake;
          create hierarchy," which is exactly why this stays a single
          low-opacity shape low in the panel, not a loud graphic
          competing with the nav links above it). Purely decorative
          (aria-hidden, pointer-events-none so it can never intercept a
          click regardless of paint order) -- deliberately not
          RTL-mirrored: it's a background texture anchored to this
          panel itself, not a directional UI cue like the back-arrow
          icons elsewhere on these pages.

          Real bug fixed here (2026-09-03): this SVG originally had
          -z-10 but <aside> only had `relative`, no z-index of its own
          -- an element needs BOTH to actually establish a new stacking
          context. Without one, the -z-10 child doesn't stay contained
          to this panel at all; it escapes upward and gets compared
          against <aside>'s OWN background in the ANCESTOR stacking
          context, where it loses and paints fully behind the sidebar's
          solid maroon fill -- rendered, but completely invisible.
          Confirmed directly, not guessed: both the JSX and the
          compiled CSS rules were verified present and correct on the
          running dev server, which is what pointed at a paint-order
          bug rather than a missing-code one. Fix is `z-0` added to
          <aside> itself (any explicit integer, including 0, makes a
          positioned element establish its own stacking context) so
          this SVG's -z-10 is now genuinely scoped to this panel: behind
          <aside>'s own background paint (correct -- that's step one of
          any stacking context regardless), still behind the header/
          nav/sign-out content that follows it in the DOM (correct --
          that's the whole point), just no longer able to escape past
          the panel's own boundary the way it did before. */}
      <svg
        aria-hidden="true"
        className="absolute -z-10 pointer-events-none left-[-90px] bottom-[-60px] h-[560px] w-[300px]"
        viewBox="0 0 200 400"
      >
        <path
          d="M 100 0 C 180 60, 180 260, 100 400 C 20 260, 20 60, 100 0 Z"
          fill="white"
          fillOpacity="0.06"
          transform="rotate(18 100 200)"
        />
      </svg>
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
          onClick={onSignOut}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-white/70 hover:bg-red-500/20 hover:text-white transition-colors"
        >
          <LogOut className="h-5 w-5" />
          <span>{t('adminLayout.signOut')}</span>
        </button>
      </div>
    </>
  );
}

/**
 * Responsive plan R0 (docs/responsive-design-plan.md): the admin chrome
 * (sidebar + header + content well), moved verbatim out of AdminLayout so
 * the DEV harness (/dev/admin-preview) can render the REAL shell without
 * a Supabase session. AdminLayout above keeps the role gate and passes
 * <Outlet /> through unchanged. Pure move: same markup, same classes.
 * R1 is where this shell's phone/tablet layout changes.
 */
export function AdminShell({ children, onSignOut }: { children: React.ReactNode; onSignOut: () => void }) {
  const { t } = useTranslation();
  const location = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const closeMenu = () => setIsMenuOpen(false);
  // Navigating from the drawer's own links closes it.
  useEffect(() => { setIsMenuOpen(false); }, [location.pathname]);

  return (
    <div className="flex h-dvh w-full bg-background text-foreground">
      {/* Sidebar: persistent at lg+; below lg it lives in the Drawer (R1,
          docs/responsive-design-plan.md) opened from the header's menu
          button, since a fixed 256px column left ~55px of content on a
          phone. Same SidebarPanel in both places. */}
      <aside className="relative z-0 hidden w-64 shrink-0 overflow-hidden border-e border-secondary-foreground/10 bg-secondary text-secondary-foreground lg:flex lg:flex-col">
        <SidebarPanel onSignOut={onSignOut} />
      </aside>
      <Drawer
        open={isMenuOpen}
        onClose={closeMenu}
        side="start"
        aria-label={t('adminLayout.menu')}
        className="lg:hidden overflow-hidden bg-secondary text-secondary-foreground border-secondary-foreground/10"
      >
        <div id="admin-mobile-menu" className="relative z-0 flex h-full flex-col overflow-hidden">
          <SidebarPanel onSignOut={onSignOut} />
        </div>
      </Drawer>

      {/* Main Content */}
      <main className="flex-1 overflow-auto bg-background flex flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4 sm:px-6 lg:h-24 lg:justify-end lg:px-8">
          {/* Below lg the sidebar (and its wordmark) is out of view, so the
              header carries the menu button and a compact wordmark. */}
          <div className="flex items-center gap-2 lg:hidden">
            <button
              type="button"
              onClick={() => setIsMenuOpen(true)}
              aria-label={t('adminLayout.openMenu')}
              aria-expanded={isMenuOpen}
              aria-controls="admin-mobile-menu"
              className="touch-target -ms-2 flex items-center justify-center rounded-md text-foreground hover:bg-muted"
            >
              <Menu className="h-5 w-5" />
            </button>
            <span className="text-lg font-bold tracking-tight text-foreground">
              <span dir="ltr" className="inline-block">e&</span> <span className="text-muted-foreground font-normal">|</span> هِمّة
            </span>
          </div>
          <LanguageToggle />
        </header>
        <div className="p-4 sm:p-6 lg:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
