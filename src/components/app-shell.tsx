"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, BookOpen, CircleUserRound, House, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { BrandLockup } from "@/components/brand-lockup";
import { useSession } from "@/components/session-provider";

const navigation = [
  { href: "/", label: "Today", icon: House },
  { href: "/learn", label: "Learn", icon: BookOpen },
  { href: "/progress", label: "Progress", icon: BarChart3 },
  { href: "/review", label: "Review", icon: RefreshCw },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const showStreak = pathname === "/";
  const { status, user } = useSession();

  return (
    <div className="app-frame">
      <header className="app-header">
        <BrandLockup />
        <div className="header-actions">
        {showStreak && (status === "authenticated" || status === "guest") ? (
          <div className="streak-pill" aria-label={status === "authenticated" ? `${user?.streakDays ?? 0} day streak` : "Example 12 day streak"}>
            <span className="streak-books" aria-hidden="true"><i /><i /></span>
            <span>{status === "authenticated" ? user?.streakDays ? `${user.streakDays} day${user.streakDays === 1 ? "" : "s"} streak` : "Start a streak" : "12 day demo"}</span>
          </div>
        ) : null}
        <Link className="account-entry" href="/account" aria-label={user ? `Account, signed in as ${user.displayName}` : "Account"} aria-current={pathname === "/account" ? "page" : undefined}>
          <CircleUserRound size={19} strokeWidth={1.9} aria-hidden="true" /><span>Account</span>
        </Link>
        </div>
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
