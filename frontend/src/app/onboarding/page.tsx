"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  addInvitedUser,
  getAccount,
  getCurrentUser,
  getInvitedUsers,
  UserRole,
} from "@/lib/auth";
import { sendUserInviteEmail } from "@/lib/notifications";

const roles: UserRole[] = ["Admin", "Editor", "Leitor"];

export default function OnboardingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("Editor");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [users, setUsers] = useState(() => getInvitedUsers());
  const [sending, setSending] = useState(false);

  useEffect(() => {
    setUsers(getInvitedUsers());
  }, []);

  const inviteUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSending(true);

    const company = getAccount()?.company;
    const inviter = getCurrentUser();
    const normalizedName = name.trim();
    const normalizedEmail = email.trim().toLowerCase();

    if (!company || !inviter) {
      setError("Sessao invalida. Faca login novamente para convidar usuarios.");
      setSending(false);
      return;
    }

    const result = addInvitedUser({ name: normalizedName, email: normalizedEmail, role });

    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel adicionar usuario.");
      setSending(false);
      return;
    }

    try {
      await sendUserInviteEmail({
        company_name: company.name,
        inviter_name: inviter.name,
        invitee_name: normalizedName,
        invitee_email: normalizedEmail,
        role,
      });
    } catch {
      // Usuario ja foi salvo; avisa que o e-mail falhou mas nao reverte
      setSuccess("Usuario adicionado. O convite por e-mail nao foi enviado — verifique a configuracao SMTP.");
      setUsers(getInvitedUsers());
      setName("");
      setEmail("");
      setRole("Editor");
      setSending(false);
      return;
    }

    setSuccess("Usuario adicionado e convite enviado por e-mail.");
    setUsers(getInvitedUsers());
    setName("");
    setEmail("");
    setRole("Editor");
    setSending(false);
  };

  return (
    <div className="min-h-screen bg-[#0b1220] bg-[radial-gradient(circle_at_top,#14243f_0%,#0b1220_50%,#090f1b_100%)] px-4 py-8 sm:py-12">
      <div className="mx-auto w-full max-w-3xl rounded-2xl border border-[#1f2d44] bg-[#0f1a2b]/95 p-6 shadow-xl sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#38bdf8]">Onboarding</p>
        <h1 className="mt-2 text-2xl font-black text-[#e2ecff]">Convide usuarios da empresa</h1>
        <p className="mt-2 text-sm text-[#9fb3cf]">
          Configure os acessos da equipe para compartilhar dados geoespaciais com seguranca.
        </p>
        {searchParams.get("welcomeEmail") === "failed" && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
            Cadastro concluido, mas o e-mail de boas-vindas nao foi enviado. Verifique a configuracao SMTP.
          </p>
        )}

        <form className="mt-6 grid gap-4 md:grid-cols-[1fr_1fr_180px_auto]" onSubmit={inviteUser}>
          <label className="block">
            <span className="text-sm font-medium text-[#c9d9ef]">Nome</span>
            <input
              type="text"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
              placeholder="Nome do usuario"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-[#c9d9ef]">E-mail</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
              placeholder="usuario@empresa.com"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-[#c9d9ef]">Perfil</span>
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as UserRole)}
              className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
            >
              {roles.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <div className="self-end">
            <button
              type="submit"
              disabled={sending}
              className="w-full rounded-lg bg-[#1d4f7a] px-4 py-2.5 text-sm font-semibold text-[#dff4ff] hover:bg-[#25608f] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {sending ? "Enviando..." : "Adicionar"}
            </button>
          </div>
        </form>

        {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        {success && <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{success}</p>}

        <div className="mt-6 overflow-hidden rounded-xl border border-[#2a3f58]">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-[#101b2c] text-left text-xs uppercase tracking-wide text-[#8fa8c6]">
              <tr>
                <th className="px-4 py-3">Nome</th>
                <th className="px-4 py-3">E-mail</th>
                <th className="px-4 py-3">Perfil</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.email} className="border-t border-[#1d2b3e] text-[#c9d9ef]">
                  <td className="px-4 py-3">{user.name}</td>
                  <td className="px-4 py-3">{user.email}</td>
                  <td className="px-4 py-3">{user.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-6 flex flex-wrap justify-between gap-3">
          <Link href="/cadastro" className="text-sm text-[#8aa2c4] hover:text-[#dbe8fb] hover:underline">
            Voltar ao cadastro
          </Link>
          <button
            onClick={() => router.push("/dashboard")}
            className="rounded-lg bg-[#1d4f7a] px-4 py-2.5 text-sm font-semibold text-[#dff4ff] hover:bg-[#25608f]"
          >
            Finalizar e acessar dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
