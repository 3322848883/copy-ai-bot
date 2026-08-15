"use client";

import AdminShell from "@/components/AdminShell";
import { ConfirmProvider } from "@/components/ConfirmDialog";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <ConfirmProvider>
      <AdminShell>{children}</AdminShell>
    </ConfirmProvider>
  );
}
