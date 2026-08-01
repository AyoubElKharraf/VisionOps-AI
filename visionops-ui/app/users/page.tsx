import { UserManager } from "@/components/UserManager";

export default function UsersPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold">Users</h1>
        <p className="mt-1 text-sm text-muted">
          Create dashboard accounts with admin or operator roles. Admin only.
        </p>
      </div>
      <UserManager />
    </div>
  );
}
