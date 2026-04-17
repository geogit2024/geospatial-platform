"use client";

import { FormEvent, useMemo, useState } from "react";
import {
  canManageUsers,
  getAccount,
  getCurrentUser,
  getInvitedUsers,
  getUserStatus,
  addInvitedUser,
  removeUser,
  resetUserPassword,
  updateUserProfile,
  updateUserRole,
  type UserProfile,
  type UserRole,
} from "@/lib/auth";
import { formatDate } from "@/lib/utils";
import { sendUserInviteEmail } from "@/lib/notifications";
import {
  AlertCircle,
  KeyRound,
  Mail,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  Users,
  X,
} from "lucide-react";

const ROLES: UserRole[] = ["Admin", "Editor", "Leitor"];

export default function UsuariosPage() {
  const [users, setUsers] = useState<UserProfile[]>(() => getInvitedUsers());
  const [query, setQuery] = useState("");

  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<UserRole>("Editor");
  const [inviteLoading, setInviteLoading] = useState(false);

  const [editingEmail, setEditingEmail] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [editingNewEmail, setEditingNewEmail] = useState("");
  const [rowBusyEmail, setRowBusyEmail] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const account = getAccount();
  const currentUser = getCurrentUser();
  const adminAllowed = canManageUsers();

  const counters = useMemo(() => {
    const total = users.length;
    const admins = users.filter((user) => user.role === "Admin").length;
    const pending = users.filter((user) => getUserStatus(user) === "pendente").length;
    return { total, admins, pending };
  }, [users]);

  const filteredUsers = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return users;
    return users.filter((user) => {
      const status = getUserStatus(user);
      return (
        user.name.toLowerCase().includes(normalized) ||
        user.email.toLowerCase().includes(normalized) ||
        user.role.toLowerCase().includes(normalized) ||
        status.includes(normalized)
      );
    });
  }, [query, users]);

  const refreshUsers = () => {
    setUsers(getInvitedUsers());
  };

  const clearMessages = () => {
    setError(null);
    setSuccess(null);
  };

  const startEdit = (user: UserProfile) => {
    clearMessages();
    setEditingEmail(user.email);
    setEditingName(user.name);
    setEditingNewEmail(user.email);
  };

  const cancelEdit = () => {
    setEditingEmail(null);
    setEditingName("");
    setEditingNewEmail("");
  };

  const onInviteUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearMessages();
    setInviteLoading(true);

    const result = addInvitedUser({
      name: inviteName,
      email: inviteEmail,
      role: inviteRole,
    });

    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel adicionar usuario.");
      setInviteLoading(false);
      return;
    }

    refreshUsers();
    setInviteName("");
    setInviteEmail("");
    setInviteRole("Editor");

    let inviteNote = "Usuario adicionado com sucesso.";
    try {
      if (account && currentUser) {
        await sendUserInviteEmail({
          company_name: account.company.name,
          inviter_name: currentUser.name,
          invitee_name: inviteName.trim(),
          invitee_email: inviteEmail.trim().toLowerCase(),
          role: inviteRole,
        });
        inviteNote = "Usuario adicionado e convite enviado por e-mail.";
      }
    } catch {
      inviteNote = "Usuario adicionado, mas houve falha no envio do convite por e-mail.";
    }

    setSuccess(inviteNote);
    setInviteLoading(false);
  };

  const onChangeRole = (email: string, nextRole: UserRole) => {
    clearMessages();
    const result = updateUserRole(email, nextRole);
    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel atualizar perfil.");
      return;
    }
    refreshUsers();
    setSuccess("Perfil atualizado.");
  };

  const onSaveEdit = () => {
    if (!editingEmail) return;
    clearMessages();

    const existing = users.find((user) => user.email === editingEmail);
    if (!existing) {
      setError("Usuario nao encontrado.");
      return;
    }

    const result = updateUserProfile({
      currentEmail: editingEmail,
      name: editingName,
      email: editingNewEmail,
      role: existing.role,
    });

    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel salvar alteracoes.");
      return;
    }

    refreshUsers();
    cancelEdit();
    setSuccess("Dados do usuario atualizados.");
  };

  const onRemoveUser = (email: string) => {
    clearMessages();
    const target = users.find((user) => user.email === email);
    if (!target) return;

    if (!confirm(`Remover o usuario ${target.name}?`)) return;

    const result = removeUser(email);
    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel remover usuario.");
      return;
    }

    refreshUsers();
    setSuccess("Usuario removido.");
  };

  const onResetAccess = (email: string) => {
    clearMessages();
    const target = users.find((user) => user.email === email);
    if (!target) return;

    const tempPassword = generateTemporaryPassword();
    const result = resetUserPassword(email, tempPassword);
    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel redefinir o acesso.");
      return;
    }

    refreshUsers();
    setSuccess(`Acesso redefinido para ${target.email}. Senha temporaria: ${tempPassword}`);
  };

  const onResendInvite = async (user: UserProfile) => {
    clearMessages();
    if (!account || !currentUser) {
      setError("Sessao invalida para reenviar convite.");
      return;
    }

    setRowBusyEmail(user.email);
    try {
      await sendUserInviteEmail({
        company_name: account.company.name,
        inviter_name: currentUser.name,
        invitee_name: user.name,
        invitee_email: user.email,
        role: user.role,
      });
      setSuccess(`Convite reenviado para ${user.email}.`);
    } catch (inviteError: unknown) {
      setError(inviteError instanceof Error ? inviteError.message : "Falha ao reenviar convite.");
    } finally {
      setRowBusyEmail(null);
    }
  };

  if (!adminAllowed) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <div className="rounded-2xl border border-[#2a3f58] bg-[#101b2c] p-6 text-[#dbe8fb]">
          <div className="flex items-center gap-2 text-[#facc15]">
            <AlertCircle className="h-5 w-5" />
            <p className="font-semibold">Acesso restrito</p>
          </div>
          <p className="mt-2 text-sm text-[#9fb3cf]">
            Apenas usuarios com perfil Admin podem acessar o modulo de gestao de usuarios.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="rounded-2xl border border-[#2a3f58] bg-[#0f1a2b] px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-black text-[#e2ecff]">Gestao de Usuarios</h1>
              <p className="mt-1 text-sm text-[#9fb3cf]">
                Convites, perfis de acesso e controle operacional da equipe.
              </p>
            </div>
            <div className="inline-flex items-center gap-2 rounded-lg border border-[#2a3f58] bg-[#13263d] px-3 py-2 text-xs text-[#9fd8ff]">
              <ShieldCheck className="h-4 w-4" />
              Empresa: {account?.company.name ?? "Workspace"}
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <KpiCard label="Usuarios" value={String(counters.total)} />
            <KpiCard label="Admins" value={String(counters.admins)} />
            <KpiCard label="Pendentes" value={String(counters.pending)} />
          </div>
        </header>

        <section className="rounded-2xl border border-[#2a3f58] bg-[#0f1a2b] p-5">
          <div className="mb-4 flex items-center gap-2 text-[#dbe8fb]">
            <UserIcon />
            <h2 className="text-lg font-bold">Novo usuario</h2>
          </div>

          <form className="grid gap-3 lg:grid-cols-[1fr_1fr_180px_auto]" onSubmit={onInviteUser}>
            <input
              type="text"
              required
              value={inviteName}
              onChange={(event) => setInviteName(event.target.value)}
              placeholder="Nome completo"
              className="rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none focus:border-[#38bdf8]"
            />

            <input
              type="email"
              required
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="usuario@empresa.com"
              className="rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none focus:border-[#38bdf8]"
            />

            <select
              value={inviteRole}
              onChange={(event) => setInviteRole(event.target.value as UserRole)}
              className="rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none focus:border-[#38bdf8]"
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>

            <button
              type="submit"
              disabled={inviteLoading}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#1d4f7a] px-4 py-2.5 text-sm font-semibold text-[#dff4ff] hover:bg-[#25608f] disabled:opacity-60"
            >
              <Plus className="h-4 w-4" />
              {inviteLoading ? "Adicionando..." : "Adicionar"}
            </button>
          </form>
        </section>

        {(error || success) && (
          <section className="space-y-2">
            {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
            {success && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{success}</p>}
          </section>
        )}

        <section className="rounded-2xl border border-[#2a3f58] bg-[#0f1a2b] p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-[#dbe8fb]">Usuarios cadastrados</h2>

            <label className="relative w-full max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#7f97b5]" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Buscar por nome, e-mail, perfil ou status"
                className="w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] py-2.5 pl-9 pr-3 text-sm text-[#e2ecff] outline-none focus:border-[#38bdf8]"
              />
            </label>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead className="bg-[#101b2c] text-left text-xs uppercase tracking-wide text-[#8fa8c6]">
                <tr>
                  <th className="px-3 py-3">Nome</th>
                  <th className="px-3 py-3">E-mail</th>
                  <th className="px-3 py-3">Perfil</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Cadastro</th>
                  <th className="px-3 py-3">Acoes</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => {
                  const isEditing = editingEmail === user.email;
                  const status = getUserStatus(user);
                  return (
                    <tr key={user.email} className="border-t border-[#1d2b3e] text-[#c9d9ef]">
                      <td className="px-3 py-3">
                        {isEditing ? (
                          <input
                            value={editingName}
                            onChange={(event) => setEditingName(event.target.value)}
                            className="w-full rounded-md border border-[#2b3f57] bg-[#0b1727] px-2 py-1.5 text-sm text-[#e2ecff] outline-none focus:border-[#38bdf8]"
                          />
                        ) : (
                          user.name
                        )}
                      </td>
                      <td className="px-3 py-3">
                        {isEditing ? (
                          <input
                            value={editingNewEmail}
                            onChange={(event) => setEditingNewEmail(event.target.value)}
                            className="w-full rounded-md border border-[#2b3f57] bg-[#0b1727] px-2 py-1.5 text-sm text-[#e2ecff] outline-none focus:border-[#38bdf8]"
                          />
                        ) : (
                          user.email
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <select
                          value={user.role}
                          onChange={(event) => onChangeRole(user.email, event.target.value as UserRole)}
                          className="rounded-md border border-[#2b3f57] bg-[#0b1727] px-2 py-1.5 text-sm text-[#e2ecff] outline-none focus:border-[#38bdf8]"
                        >
                          {ROLES.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-3">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${
                            status === "ativo"
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-amber-100 text-amber-700"
                          }`}
                        >
                          {status}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-[#9fb3cf]">{formatDate(user.invitedAt)}</td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap gap-1">
                          {isEditing ? (
                            <>
                              <button
                                onClick={onSaveEdit}
                                className="rounded-md border border-[#2a3f58] bg-[#13263d] p-2 text-[#8ad3ff] hover:bg-[#19324f]"
                                title="Salvar"
                              >
                                <Save className="h-4 w-4" />
                              </button>
                              <button
                                onClick={cancelEdit}
                                className="rounded-md border border-[#2a3f58] bg-[#13263d] p-2 text-[#9fb3cf] hover:bg-[#19324f]"
                                title="Cancelar"
                              >
                                <X className="h-4 w-4" />
                              </button>
                            </>
                          ) : (
                            <button
                              onClick={() => startEdit(user)}
                              className="rounded-md border border-[#2a3f58] bg-[#13263d] p-2 text-[#8ad3ff] hover:bg-[#19324f]"
                              title="Editar"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                          )}

                          <button
                            onClick={() => onResetAccess(user.email)}
                            className="rounded-md border border-[#2a3f58] bg-[#13263d] p-2 text-[#9fd8ff] hover:bg-[#19324f]"
                            title="Resetar acesso"
                          >
                            <KeyRound className="h-4 w-4" />
                          </button>

                          <button
                            onClick={() => onResendInvite(user)}
                            disabled={rowBusyEmail === user.email}
                            className="rounded-md border border-[#2a3f58] bg-[#13263d] p-2 text-[#9fd8ff] hover:bg-[#19324f] disabled:opacity-60"
                            title="Reenviar convite"
                          >
                            {rowBusyEmail === user.email ? (
                              <RotateCcw className="h-4 w-4 animate-spin" />
                            ) : (
                              <Mail className="h-4 w-4" />
                            )}
                          </button>

                          <button
                            onClick={() => onRemoveUser(user.email)}
                            className="rounded-md border border-[#2a3f58] bg-[#13263d] p-2 text-[#fca5a5] hover:bg-[#19324f]"
                            title="Remover"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#2a3f58] bg-[#101b2c] px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-[#8fa8c6]">{label}</p>
      <p className="mt-1 text-xl font-black text-[#e2ecff]">{value}</p>
    </div>
  );
}

function UserIcon() {
  return (
    <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#13263d] text-[#38bdf8]">
      <Users className="h-4 w-4" />
    </span>
  );
}

function generateTemporaryPassword() {
  const rand = Math.random().toString(36).slice(-6);
  return `Geo@${rand}9`;
}
