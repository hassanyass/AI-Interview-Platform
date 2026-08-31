import { Link, useLocation, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

export function AppShell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { signOut, user } = useAuth();

  const navItems: Array<{name: string, path: string, icon: any}> = [];

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-[#f5f7fa] text-foreground">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex h-[72px] max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2.5" aria-label="e& Himma home">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white shadow-sm"><span dir="ltr">e&</span></span>
              <span className="text-[17px] font-bold tracking-tight text-slate-950">هِمّة</span>
            </div>
            <nav className="hidden items-center gap-1 md:flex" aria-label="Primary navigation">
              {navItems.map(({ name, path, icon: Icon }) => {
                const isActive = location.pathname.startsWith(path);
                return <Link key={path} to={path} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? "bg-slate-100 text-slate-950" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}><Icon className="h-4 w-4" />{name}</Link>;
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2.5 border-e border-slate-200 pe-4 sm:flex"><span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">{(user?.email?.[0] || "U").toUpperCase()}</span><span className="max-w-[180px] truncate text-sm font-medium text-slate-600">{user?.email}</span></div>
            <button type="button" onClick={handleSignOut} title="Sign out" className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-900"><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-[1480px] gap-1 overflow-x-auto px-4 pb-2 md:hidden sm:px-6" aria-label="Mobile navigation">
          {navItems.map(({ name, path, icon: Icon }) => <Link key={path} to={path} className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium ${location.pathname.startsWith(path) ? "bg-slate-100 text-slate-950" : "text-slate-500"}`}><Icon className="h-3.5 w-3.5" />{name}</Link>)}
        </nav>
      </header>
      <main className="mx-auto w-full max-w-[1480px] px-4 py-7 sm:px-6 lg:px-8 lg:py-10">{children}</main>
    </div>
  );
}
