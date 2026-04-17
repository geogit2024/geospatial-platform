"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { login } from "@/lib/auth";

export default function AcessoPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextUrl = useMemo(() => searchParams.get("next") || "/dashboard", [searchParams]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const result = login(email, password);

    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel acessar.");
      setLoading(false);
      return;
    }

    router.push(nextUrl);
  };

  return (
    <div className="min-h-screen bg-[#0b1220] bg-[radial-gradient(circle_at_top,#14243f_0%,#0b1220_50%,#090f1b_100%)] px-4 py-8 sm:py-14">
      <div className="mx-auto w-full max-w-md rounded-2xl border border-[#1f2d44] bg-[#0f1a2b]/95 p-6 shadow-xl sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#38bdf8]">Area do cliente</p>
        <h1 className="mt-2 text-2xl font-black text-[#e2ecff]">Entrar na plataforma</h1>
        <p className="mt-2 text-sm text-[#9fb3cf]">Acesse seus dados geoespaciais com seguranca e rapidez.</p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <label className="block">
            <span className="text-sm font-medium text-[#c9d9ef]">E-mail corporativo</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
              placeholder="voce@empresa.com"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-[#c9d9ef]">Senha</span>
            <input
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
              placeholder="Digite sua senha"
            />
          </label>

          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-[#1d4f7a] px-4 py-2.5 text-sm font-semibold text-[#dff4ff] hover:bg-[#25608f] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Validando..." : "Entrar"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-[#9fb3cf]">
          Ainda nao possui conta?{" "}
          <Link href="/cadastro" className="font-semibold text-[#38bdf8] hover:underline">
            Cadastre sua empresa
          </Link>
        </p>

        <Link href="/" className="mt-4 block text-center text-xs text-[#8aa2c4] hover:text-[#dbe8fb] hover:underline">
          Voltar para a landing page
        </Link>
      </div>
    </div>
  );
}
