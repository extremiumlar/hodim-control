import { useState } from "react";
import CrmMappingSection from "@/components/users/CrmMappingSection";
import UserCreateForm from "@/components/users/UserCreateForm";
import UsersTable from "@/components/users/UsersTable";
import { useAuth } from "@/lib/auth";

export default function Users() {
  const { user: currentUser } = useAuth();
  const isBoss = currentUser?.role === "boss";
  const isDasturchi = currentUser?.role === "dasturchi";
  // Dasturchi — Boshliq bilan bir xil (aslida undan ham kengroq: majburiy o'chirish
  // huquqi bilan) to'liq boshqaruv huquqiga ega.
  const hasFullControl = isBoss || isDasturchi;
  const canCreateUser = currentUser?.role === "hr" || hasFullControl;
  // Lavozim biriktirish: HR/Boshliq/Dasturchi (backend PATCH /users/{id}/position bilan mos)
  const canSetPosition = canCreateUser;

  const [lastInviteLink, setLastInviteLink] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      {lastInviteLink && (
        <div className="break-all rounded border border-emerald-200 bg-emerald-50 p-3 text-xs">
          <p className="mb-1 font-medium text-emerald-700">Bot havolasi:</p>
          <a href={lastInviteLink} target="_blank" rel="noreferrer" className="text-emerald-800 underline">
            {lastInviteLink}
          </a>
        </div>
      )}

      <div className={canCreateUser ? "grid gap-6 md:grid-cols-3" : ""}>
        {canCreateUser && (
          <div className="md:col-span-1">
            <UserCreateForm hasFullControl={hasFullControl} onInviteLink={setLastInviteLink} />
          </div>
        )}
        <div className={canCreateUser ? "md:col-span-2" : ""}>
          <UsersTable
            hasFullControl={hasFullControl}
            isDasturchi={isDasturchi}
            canSetPosition={canSetPosition}
            onInviteLink={setLastInviteLink}
          />
        </div>
      </div>

      {hasFullControl && <CrmMappingSection />}
    </div>
  );
}
