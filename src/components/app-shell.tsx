"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, BookOpen, House, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { BrandLockup } from "@/components/brand-lockup";

const navigation = [
  { href: "/", label: "Today", icon: House },
  { href: "/learn", label: "Learn", icon: BookOpen },
  { href: "/progress", label: "Progress", icon: BarChart3 },
  { href: "/review", label: "Review", icon: RefreshCw },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const showStreak = pathname === "/";

  return (
    <div className="app-frame">
      <header className="app-header">
        <BrandLockup />
        {showStreak ? (
          <div className="streak-pill" aria-label="12 day streak">
            <span className="streak-books" aria-hidden="true"><i /><i /></span>
            <span>12 day streak</span>
          </div>
        ) : null}
      </header>

      <main className="app-main">{children}</main>

      <nav className="tabbar" aria-label="Main navigation">
        {navigation.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              className={`tab-link${active ? " is-active" : ""}`}
              href={href}
              aria-current={active ? "page" : undefined}
            >
              <span className="tab-icon-wrap"><Icon size={20} strokeWidth={2} aria-hidden="true" /></span>
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
