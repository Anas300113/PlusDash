import type { Metadata } from "next";
import { AccountScreen } from "@/components/account-screen";

export const metadata: Metadata = { title: "Account" };

type AccountPageProps = { searchParams: Promise<{ auth?: string | string[] }> };

export default async function AccountPage({ searchParams }: AccountPageProps) {
  const params = await searchParams;
  const authResult = typeof params.auth === "string" ? params.auth : undefined;
  return <AccountScreen authResult={authResult} />;
}
