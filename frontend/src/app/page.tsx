import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  CircleCheck,
  CloudUpload,
  FolderOpen,
  GitMerge,
  Layers,
  MousePointerClick,
  Radio,
  ScanSearch,
  ServerOff,
  Settings2,
  Share2,
  X,
} from "lucide-react";

const CARD_STYLE = {
  boxShadow: "0 0 18px rgba(34,211,238,0.18), inset 0 0 18px rgba(34,211,238,0.04)",
} as const;

const STEP_BADGE_STYLE = {
  boxShadow: "0 0 10px rgba(34,211,238,0.4)",
} as const;

export default function LandingPage() {
  return (
    <div className="landing-premium-root relative min-h-screen overflow-hidden">
      <div className="landing-grid-overlay pointer-events-none absolute inset-0" />

      <div className="relative flex flex-col min-h-screen">
        <header className="flex justify-end items-center px-8 py-4 border-b border-[#1c2e47]/60">
          <div className="flex items-center gap-3">
            <Link
              href="/acesso"
              className="px-4 py-2 text-sm text-[#9ab0ce] hover:text-[#e2ecff] transition-colors"
            >
              Entrar
            </Link>
            <Link
              href="/cadastro"
              className="landing-btn-primary inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
            >
              Começar grátis
            </Link>
          </div>
        </header>

        <section className="text-center px-6 py-20 max-w-4xl mx-auto">
          <div className="relative mx-auto mb-8 h-36 w-72">
            <Image
              src="/logo_geopublish.png"
              alt="GeoPublish"
              fill
              className="object-contain"
              priority
            />
          </div>
          <span className="inline-flex rounded-full border border-[#2d4f78] bg-[#10243e] px-3 py-1 text-xs font-semibold text-[#9bd6ff] mb-6">
            Plataforma WebGIS para operação corporativa
          </span>
          <h1 className="text-4xl sm:text-5xl font-black leading-tight text-[#e6f1ff] mb-6">
            Suas imagens de satélite,
            <br />
            organizadas e prontas para usar
          </h1>
          <p className="text-lg text-[#9eb9d9] mb-10 max-w-2xl mx-auto leading-relaxed">
            <span className="block font-semibold text-[#e6f1ff] mb-2">
              Simples para você publicar. Potente para o seu negócio funcionar.
            </span>
            Leve seus dados geográficos e imagens de satélite para a web com a tranquilidade de uma infraestrutura de alto desempenho e disponibilidade total.
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <Link
              href="/cadastro"
              className="landing-btn-primary inline-flex items-center gap-2 px-6 py-3 rounded-2xl font-semibold"
            >
              Começar grátis
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/acesso"
              className="landing-btn-secondary inline-flex items-center gap-2 px-6 py-3 rounded-2xl"
            >
              Já tenho conta
            </Link>
          </div>
          <div className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-[#9bb6d4]">
            <span className="inline-flex items-center gap-1">
              <CircleCheck className="h-3.5 w-3.5 text-[#22d3ee]" />
              Setup em minutos
            </span>
            <span className="inline-flex items-center gap-1">
              <CircleCheck className="h-3.5 w-3.5 text-[#22d3ee]" />
              Publicação OGC pronta
            </span>
            <span className="inline-flex items-center gap-1">
              <CircleCheck className="h-3.5 w-3.5 text-[#22d3ee]" />
              100% local, sem cloud
            </span>
          </div>
        </section>

        <section className="px-6 pb-16">
          <div className="max-w-5xl mx-auto grid md:grid-cols-3 gap-4">
            {[
              {
                num: "1",
                icon: <CloudUpload className="h-14 w-14 text-[#22d3ee] mt-4" strokeWidth={1.2} />,
                title: "Envie",
                desc: "Arraste seus arquivos GeoTIFF, Shapefile ou GeoJSON. Sem configuração.",
              },
              {
                num: "2",
                icon: <GitMerge className="h-14 w-14 text-[#22d3ee] mt-4" strokeWidth={1.2} />,
                title: "Organize",
                desc: "O sistema processa e organiza tudo automaticamente via pipeline GDAL.",
              },
              {
                num: "3",
                icon: <Radio className="h-14 w-14 text-[#22d3ee] mt-4" strokeWidth={1.2} />,
                title: "Compartilhe",
                desc: "Visualize no mapa ou distribua via WMS, WFS e WMTS com um link.",
              },
            ].map(({ num, icon, title, desc }) => (
              <div
                key={num}
                className="relative flex flex-col items-center gap-5 rounded-2xl border border-[#1a9db8] bg-[#07182a] p-6 text-center"
                style={CARD_STYLE}
              >
                <span
                  className="absolute -top-4 inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#1a9db8] bg-[#07182a] text-[#22d3ee] font-black text-sm"
                  style={STEP_BADGE_STYLE}
                >
                  {num}
                </span>
                {icon}
                <div>
                  <h3 className="text-lg font-bold text-[#e6f1ff] mb-1">{title}</h3>
                  <p className="text-sm text-[#9db8d8] leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="px-6 pb-16">
          <div className="max-w-5xl mx-auto">
            <h3 className="text-2xl font-black text-[#e6f1ff] text-center mb-2">Cansado disso?</h3>
            <p className="text-center text-sm text-[#7bb8e8] mb-10">
              Problemas reais que o GeoPublish resolve.
            </p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                {
                  icon: <FolderOpen className="h-14 w-14 text-[#22d3ee] mt-2" strokeWidth={1.2} />,
                  desc: "Arquivos perdidos no computador ou em pastas sem padrão.",
                },
                {
                  icon: <ScanSearch className="h-14 w-14 text-[#22d3ee] mt-2" strokeWidth={1.2} />,
                  desc: "Dificuldade para encontrar imagens antigas por área ou data.",
                },
                {
                  icon: <Share2 className="h-14 w-14 text-[#22d3ee] mt-2" strokeWidth={1.2} />,
                  desc: "Compartilhar dados geoespaciais é complicado e lento.",
                },
                {
                  icon: <Settings2 className="h-14 w-14 text-[#22d3ee] mt-2" strokeWidth={1.2} />,
                  desc: "Sistemas GIS difíceis de configurar e manter.",
                },
              ].map(({ icon, desc }) => (
                <div
                  key={desc}
                  className="relative flex flex-col items-center gap-6 rounded-2xl border border-[#1a9db8] bg-[#07182a] p-6 text-center"
                  style={CARD_STYLE}
                >
                  <X className="absolute top-3 left-3 h-4 w-4 text-[#22d3ee] opacity-70" />
                  {icon}
                  <p className="text-sm text-[#b8d4e8] leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="px-6 pb-16">
          <div className="max-w-5xl mx-auto">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#38bdf8] text-center mb-2">
              A solução
            </p>
            <h3 className="text-2xl font-black text-[#e6f1ff] text-center mb-2">
              Uma solução simples de verdade
            </h3>
            <p className="text-center text-sm text-[#7bb8e8] mb-10">
              Encontre qualquer imagem em segundos, processe automaticamente e compartilhe com sua equipe
              sem complicação — tudo rodando local, sem depender de cloud.
            </p>
            <div className="grid sm:grid-cols-3 gap-4">
              {[
                {
                  icon: <MousePointerClick className="h-14 w-14 text-[#22d3ee] mt-2" strokeWidth={1.2} />,
                  value: "3 cliques",
                  sub: "do upload à publicação OGC",
                },
                {
                  icon: <Layers className="h-14 w-14 text-[#22d3ee] mt-2" strokeWidth={1.2} />,
                  value: "WMS · WFS · WMTS · WCS",
                  sub: "padrões OGC nativos",
                },
                {
                  icon: <ServerOff className="h-14 w-14 text-[#22d3ee] mt-2" strokeWidth={1.2} />,
                  value: "100% local",
                  sub: "sem dependência de cloud",
                },
              ].map(({ icon, value, sub }) => (
                <div
                  key={value}
                  className="relative flex flex-col items-center gap-6 rounded-2xl border border-[#1a9db8] bg-[#07182a] p-6 text-center"
                  style={CARD_STYLE}
                >
                  {icon}
                  <div>
                    <p className="text-lg font-black text-[#22d3ee]">{value}</p>
                    <p className="mt-1 text-xs text-[#b8d4e8]">{sub}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="px-6 pb-16 mt-auto">
          <div className="max-w-3xl mx-auto landing-panel rounded-3xl border border-[#1c3150] p-10 text-center">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#7bb8e8] mb-3">
              Pronto para começar
            </p>
            <h3 className="text-3xl font-black text-[#e6f1ff] mb-4">Comece agora</h3>
            <p className="text-[#9eb9d9] mb-8 max-w-xl mx-auto">
              Crie sua conta e publique sua primeira imagem em minutos.
            </p>
            <div className="flex flex-wrap justify-center gap-4">
              <Link
                href="/cadastro"
                className="landing-btn-primary inline-flex items-center gap-2 px-8 py-3 rounded-2xl font-semibold"
              >
                Criar conta grátis
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/acesso"
                className="landing-btn-secondary inline-flex items-center gap-2 px-8 py-3 rounded-2xl"
              >
                Já tenho conta
              </Link>
            </div>
          </div>
        </section>

        <footer className="text-center text-sm text-[#4a6580] py-6 border-t border-[#1c2e47]/60">
          © 2026 GeoPublish. Todos os direitos reservados.
        </footer>
      </div>
    </div>
  );
}
