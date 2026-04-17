"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { isAuthenticated } from "@/lib/auth";

const PUBLIC_PATHS = ["/", "/acesso", "/cadastro", "/onboarding"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [allowed, setAllowed] = useState(false);

  const isPublicRoute = useMemo(
    () => PUBLIC_PATHS.includes(pathname ?? "/"),
    [pathname]
  );

  useEffect(() => {
    if (isPublicRoute) {
      setAllowed(true);
      setChecked(true);
      return;
    }

    const auth = isAuthenticated();
    setAllowed(auth);
    setChecked(true);

    if (!auth) {
      const next = encodeURIComponent(pathname || "/dashboard");
      router.replace(`/acesso?next=${next}`);
    }
  }, [isPublicRoute, pathname, router]);

  if (!checked) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[#0b1220]">
        <p className="text-sm text-slate-300">Carregando ambiente...</p>
      </main>
    );
  }

  if (isPublicRoute) {
    return <main className="min-h-screen">{children}</main>;
  }

  if (!allowed) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[#0b1220]">
        <p className="text-sm text-slate-300">Redirecionando para o acesso...</p>
      </main>
    );
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-[#0b1220] bg-[radial-gradient(circle_at_top,#14243f_0%,#0b1220_50%,#090f1b_100%)]">
        {children}
      </main>
    </div>
  );
}
