"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import {
  CompanySegment,
  CompanySize,
  registerCompanyAndAdmin,
} from "@/lib/auth";
import { sendAdminWelcomeEmail } from "@/lib/notifications";

const segmentOptions: CompanySegment[] = [
  "Agronegocio",
  "Mineracao",
  "Meio Ambiente",
  "Engenharia e Infraestrutura",
  "Geotecnologia (GIS)",
  "Outro",
];

const sizeOptions: CompanySize[] = ["Pequena", "Media", "Grande"];

export default function CadastroPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);

  const [companyName, setCompanyName] = useState("");
  const [segment, setSegment] = useState<CompanySegment>("Agronegocio");
  const [size, setSize] = useState<CompanySize>("Media");
  const [country, setCountry] = useState("Brasil");

  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const nextFromCompany = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (!companyName.trim()) {
      setError("Informe o nome da empresa para continuar.");
      return;
    }

    setStep(2);
  };

  const finishRegistration = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("A senha deve ter no minimo 8 caracteres.");
      return;
    }

    if (password !== confirmPassword) {
      setError("As senhas nao conferem.");
      return;
    }

    if (!acceptTerms) {
      setError("Aceite os termos para concluir o cadastro.");
      return;
    }

    setLoading(true);

    const normalizedCompanyName = companyName.trim();
    const normalizedAdminEmail = adminEmail.trim().toLowerCase();
    const normalizedAdminName = adminName.trim();

    const result = await registerCompanyAndAdmin({
      company: {
        name: normalizedCompanyName,
        segment,
        size,
        country,
      },
      admin: {
        name: normalizedAdminName,
        email: normalizedAdminEmail,
        password,
      },
    });

    if (!result.ok) {
      setError(result.error ?? "Nao foi possivel concluir o cadastro.");
      setLoading(false);
      return;
    }

    let emailStatus = "sent";
    try {
      await sendAdminWelcomeEmail({
        company_name: normalizedCompanyName,
        admin_name: normalizedAdminName,
        admin_email: normalizedAdminEmail,
      });
    } catch {
      emailStatus = "failed";
    }

    router.push(`/onboarding?welcomeEmail=${emailStatus}`);
  };

  return (
    <div className="min-h-screen bg-[#0b1220] bg-[radial-gradient(circle_at_top,#14243f_0%,#0b1220_50%,#090f1b_100%)] px-4 py-8 sm:py-12">
      <div className="mx-auto w-full max-w-2xl rounded-2xl border border-[#1f2d44] bg-[#0f1a2b]/95 p-6 shadow-xl sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#38bdf8]">Teste gratis</p>
        <h1 className="mt-2 text-2xl font-black text-[#e2ecff]">Cadastro da empresa</h1>
        <p className="mt-2 text-sm text-[#9fb3cf]">
          Configure seu workspace geoespacial em minutos e acesse suas imagens em 3 cliques.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-2">
          {[1, 2].map((value) => (
            <div
              key={value}
              className={`rounded-lg border px-3 py-2 text-center text-xs font-semibold ${
                step >= value
                  ? "border-[#2c567f] bg-[#13263d] text-[#9fd8ff]"
                  : "border-[#263850] bg-[#0f1a2b] text-[#7f97b5]"
              }`}
            >
              Etapa {value}
            </div>
          ))}
        </div>

        {step === 1 && (
          <form className="mt-6 space-y-4" onSubmit={nextFromCompany}>
            <label className="block">
              <span className="text-sm font-medium text-[#c9d9ef]">Nome da empresa</span>
              <input
                type="text"
                required
                value={companyName}
                onChange={(event) => setCompanyName(event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
                placeholder="Ex.: GeoDados Inteligentes"
              />
            </label>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-sm font-medium text-[#c9d9ef]">Segmento</span>
                <select
                  value={segment}
                  onChange={(event) => setSegment(event.target.value as CompanySegment)}
                  className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
                >
                  {segmentOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-sm font-medium text-[#c9d9ef]">Porte da empresa</span>
                <select
                  value={size}
                  onChange={(event) => setSize(event.target.value as CompanySize)}
                  className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
                >
                  {sizeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="block">
              <span className="text-sm font-medium text-[#c9d9ef]">Pais</span>
              <input
                type="text"
                required
                value={country}
                onChange={(event) => setCountry(event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
              />
            </label>

            {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

            <button
              type="submit"
              className="w-full rounded-lg bg-[#1d4f7a] px-4 py-2.5 text-sm font-semibold text-[#dff4ff] hover:bg-[#25608f]"
            >
              Continuar para usuario administrador
            </button>
          </form>
        )}

        {step === 2 && (
          <form className="mt-6 space-y-4" onSubmit={finishRegistration}>
            <label className="block">
              <span className="text-sm font-medium text-[#c9d9ef]">Nome do administrador</span>
              <input
                type="text"
                required
                value={adminName}
                onChange={(event) => setAdminName(event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
                placeholder="Nome completo"
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium text-[#c9d9ef]">E-mail corporativo</span>
              <input
                type="email"
                required
                value={adminEmail}
                onChange={(event) => setAdminEmail(event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
                placeholder="admin@empresa.com"
              />
            </label>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-sm font-medium text-[#c9d9ef]">Senha</span>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-[#c9d9ef]">Confirmar senha</span>
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-[#2b3f57] bg-[#0b1727] px-3 py-2.5 text-sm text-[#e2ecff] outline-none transition focus:border-[#38bdf8] focus:ring-2 focus:ring-[#14324f]"
                />
              </label>
            </div>

            <label className="flex items-start gap-2 text-sm text-[#9fb3cf]">
              <input
                type="checkbox"
                checked={acceptTerms}
                onChange={(event) => setAcceptTerms(event.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-[#2b3f57] bg-[#0b1727] text-[#38bdf8] focus:ring-[#2c567f]"
              />
              <span>Aceito os termos de uso e politicas de protecao de dados (LGPD).</span>
            </label>

            {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => {
                  setError(null);
                  setStep(1);
                }}
                className="rounded-lg border border-[#2a3f58] px-4 py-2.5 text-sm font-semibold text-[#9fb3cf] hover:bg-[#122033]"
              >
                Voltar
              </button>
              <button
                type="submit"
                disabled={loading}
                className="rounded-lg bg-[#1d4f7a] px-4 py-2.5 text-sm font-semibold text-[#dff4ff] hover:bg-[#25608f] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? "Concluindo..." : "Concluir cadastro"}
              </button>
            </div>
          </form>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-2 text-sm">
          <Link href="/" className="text-[#8aa2c4] hover:text-[#dbe8fb] hover:underline">
            Voltar para a landing
          </Link>
          <Link href="/acesso" className="font-semibold text-[#38bdf8] hover:underline">
            Ja tenho conta
          </Link>
        </div>
      </div>
    </div>
  );
}
