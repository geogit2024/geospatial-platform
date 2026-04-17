"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LayoutDashboard, Upload, Map, Globe, LogOut, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { getAccount, getCurrentUser, logout } from "@/lib/auth";

const links = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/map", label: "Mapa WebGIS", icon: Map },
  { href: "/usuarios", label: "Usuarios", icon: Users },
];

export default function Sidebar() {
  const path = usePathname();
  const router = useRouter();
  const [companyName, setCompanyName] = useState("Workspace");
  const [userName, setUserName] = useState("Usuario");

  useEffect(() => {
    const company = getAccount()?.company;
    const user = getCurrentUser();

    if (company?.name) setCompanyName(company.name);
    if (user?.name) setUserName(user.name);
  }, []);

  const handleLogout = () => {
    logout();
    router.push("/acesso");
  };

  return (
    <aside className="w-56 flex flex-col bg-[#0f172a] text-[#e2ecff] shrink-0 border-r border-[#1e2a3f]">
      <div className="flex items-center gap-2 px-5 py-5 border-b border-[#1e2a3f]">
        <Globe className="w-6 h-6 text-[#38bdf8]" />
        <div className="min-w-0">
          <span className="font-bold text-lg tracking-tight block">GeoPublish</span>
          <p className="text-[11px] text-[#8aa2c4] truncate">{companyName}</p>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
              path.startsWith(href)
                ? "bg-[#13263d] text-[#e6f4ff] border border-[#2c567f]"
                : "text-[#9ab0ce] hover:bg-[#122033] hover:text-[#e2ecff]"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>

      <div className="px-3 pb-3">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-[#9ab0ce] hover:bg-[#122033] hover:text-[#e2ecff]"
        >
          <LogOut className="w-4 h-4" />
          Sair
        </button>
      </div>

      <div className="px-5 py-4 border-t border-[#1e2a3f] text-xs text-[#7f98b7]">
        <p className="truncate">{userName}</p>
        <p className="mt-1">OGC WMS - WMTS - WCS</p>
      </div>
    </aside>
  );
}
