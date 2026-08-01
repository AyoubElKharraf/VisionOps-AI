"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { AuthUserProfile, AuthUserRole, UserInput } from "@/lib/api";
import { visionopsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const emptyForm: UserInput = {
  username: "",
  password: "",
  full_name: "",
  role: "operator",
  is_active: true,
};

export function UserManager() {
  const { isAdmin, ready } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<AuthUserProfile[]>([]);
  const [form, setForm] = useState<UserInput>(emptyForm);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return;
    if (!isAdmin) {
      router.replace("/");
    }
  }, [ready, isAdmin, router]);

  const reload = async () => {
    try {
      setLoading(true);
      setUsers(await visionopsApi.listUsers());
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!ready || !isAdmin) return;
    void reload();
  }, [ready, isAdmin]);

  const create = async () => {
    if (!form.username.trim() || form.password.length < 8) {
      setStatus("Username required; password must be at least 8 characters");
      return;
    }
    try {
      await visionopsApi.createUser({
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name?.trim() || null,
        role: form.role ?? "operator",
        is_active: form.is_active ?? true,
      });
      setForm(emptyForm);
      setStatus("User created");
      await reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Create failed");
    }
  };

  if (!ready || !isAdmin) {
    return (
      <p className="text-sm text-muted">
        Admin access required. Redirecting…
      </p>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted">
            Admins manage dashboard accounts. Operators monitor and handle
            incidents; they cannot manage cameras or users.
          </p>
          <button
            type="button"
            onClick={() => void reload()}
            className="min-h-11 rounded-md border border-white/15 px-3 text-sm hover:bg-white/5"
          >
            Refresh
          </button>
        </div>

        {loading && <p className="text-sm text-muted">Loading users…</p>}

        {!loading && users.length === 0 && (
          <p className="rounded-md border border-dashed border-white/15 px-4 py-6 text-sm text-muted">
            No users yet. Create an operator account to share the Control Center.
          </p>
        )}

        <div className="space-y-3">
          {users.map((u) => (
            <article
              key={u.id}
              className="rounded-lg border border-white/10 bg-panel/60 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-lg font-semibold">
                    {u.full_name || u.username}
                  </h2>
                  <p className="mt-1 text-xs text-muted">
                    <code className="text-accent">{u.username}</code>
                    {" · "}
                    <span className="text-accent">{u.role}</span>
                    {" · "}
                    <span className={u.is_active ? "text-accent" : "text-amber-300"}>
                      {u.is_active ? "active" : "inactive"}
                    </span>
                  </p>
                  <p className="mt-2 text-xs text-muted">
                    Created {new Date(u.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>

      <div className="space-y-4 rounded-lg border border-white/10 bg-panel/50 p-4">
        <h2 className="font-display text-lg font-semibold">Add user</h2>
        <label className="block text-sm">
          Username
          <input
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            autoComplete="off"
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="block text-sm">
          Full name
          <input
            value={form.full_name ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            autoComplete="new-password"
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="block text-sm">
          Role
          <select
            value={form.role ?? "operator"}
            onChange={(e) =>
              setForm((f) => ({ ...f, role: e.target.value as AuthUserRole }))
            }
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          >
            <option value="operator">operator</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_active ?? true}
            onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            className="h-4 w-4 accent-[var(--tw-accent,#3dd6c6)]"
          />
          Active
        </label>
        <button
          type="button"
          onClick={() => void create()}
          className="min-h-11 w-full rounded-md bg-accent px-4 text-sm font-medium text-ink hover:opacity-90"
        >
          Create user
        </button>
        {status && <p className="text-xs text-accent">{status}</p>}
      </div>
    </div>
  );
}
