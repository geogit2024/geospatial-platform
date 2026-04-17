import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  Database,
  FolderSearch,
  Globe2,
  HardDriveDownload,
  Layers3,
  Server,
  ShieldCheck,
  Share2,
  Workflow,
} from "lucide-react";

const proofItems = [
  {
    icon: HardDriveDownload,
    title: "Sem infraestrutura local",
    subtitle: "Storage, publicacao e acesso em nuvem gerenciada.",
  },
  {
    icon: Workflow,
    title: "Recuperacao em 3 cliques",
    subtitle: "Upload, busca e visualizacao com fluxo objetivo.",
  },
  {
    icon: Clock3,
    title: "Entrega operacional rapida",
    subtitle: "Camadas prontas para consumo tecnico e negocio.",
  },
];

const problemSolution = [
  {
    problem: "Arquivos espalhados e sem padrao de organizacao.",
    solution: "Catalogacao por metadados e historico centralizado por tenant.",
  },
  {
    problem: "Horas para localizar imagens antigas.",
    solution: "Busca orientada por area, data, CRS e contexto de publicacao.",
  },
  {
    problem: "Dependencia de infraestrutura propria para servir dados.",
    solution: "Servicos WMS/WMTS/WCS publicados com endpoint pronto para GIS.",
  },
];

const executionSteps = [
  {
    icon: Database,
    title: "1. Upload simplificado",
    detail: "Envie GeoTIFF em lote com metadados essenciais.",
  },
  {
    icon: FolderSearch,
    title: "2. Organizacao inteligente",
    detail: "Classifique rapidamente por projeto, area e periodo.",
  },
  {
    icon: Share2,
    title: "3. Compartilhamento imediato",
    detail: "Publique e distribua camadas para equipes e clientes.",
  },
];

const differentiators = [
  { icon: Globe2, title: "Escala global", detail: "Arquitetura preparada para operacao multi-projeto." },
  { icon: Layers3, title: "OGC nativo", detail: "Integre em ArcGIS, QGIS e stacks WebGIS." },
  { icon: ShieldCheck, title: "Governanca", detail: "Controle de acesso, rastreabilidade e LGPD." },
  { icon: Server, title: "Baixo custo operacional", detail: "Sem capex de infraestrutura dedicada." },
];

export default function Home() {
  return (
    <div className="landing-premium-root relative min-h-screen overflow-hidden px-4 py-8 sm:px-8 sm:py-10">
      <div className="landing-grid-overlay pointer-events-none absolute inset-0" />

      <div className="relative mx-auto flex w-full max-w-6xl flex-col gap-6">
        <section className="landing-panel rounded-3xl border border-[#1c3150] p-6 sm:p-8">
          <div className="grid items-center gap-8 lg:grid-cols-[1.05fr_0.95fr]">
            <div>
              <p className="inline-flex rounded-full border border-[#2d4f78] bg-[#10243e] px-3 py-1 text-xs font-semibold text-[#9bd6ff]">
                Plataforma SaaS para operacao geoespacial empresarial
              </p>

              <h1 className="mt-4 text-4xl font-black leading-tight text-[#e6f1ff] sm:text-5xl">
                Transforme imagens de satelite em dados acionaveis em segundos
              </h1>

              <p className="mt-4 max-w-2xl text-sm leading-relaxed text-[#9eb9d9] sm:text-base">
                Organize, visualize e compartilhe suas imagens com eficiencia e controle total.
                Sem infraestrutura, sem complexidade - apenas resultados.
              </p>

              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  href="/cadastro"
                  className="landing-btn-primary inline-flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold"
                >
                  Comecar teste gratis
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  href="/acesso"
                  className="landing-btn-secondary inline-flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold"
                >
                  Entrar na plataforma
                </Link>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[#9bb6d4]">
                <span className="inline-flex items-center gap-1">
                  <CheckCircle2 className="h-3.5 w-3.5 text-[#22d3ee]" />
                  Setup inicial em minutos
                </span>
                <span className="inline-flex items-center gap-1">
                  <CheckCircle2 className="h-3.5 w-3.5 text-[#22d3ee]" />
                  Publicacao OGC pronta
                </span>
                <span className="inline-flex items-center gap-1">
                  <CheckCircle2 className="h-3.5 w-3.5 text-[#22d3ee]" />
                  Foco em operacao B2B
                </span>
              </div>
            </div>

            <div className="relative">
              <div className="landing-hero-frame relative mx-auto h-[320px] w-full max-w-[520px] overflow-hidden rounded-2xl border border-[#2c4d73]">
                <Image
                  src="/landing/globo.jpg"
                  alt="Visao global com rede de dados geoespaciais e analytics"
                  fill
                  priority
                  className="object-cover"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-[#071325]/65 via-[#091a30]/20 to-transparent" />
              </div>

              <div className="landing-float-chip left-3 top-3">
                <span className="text-[10px] uppercase tracking-wide text-[#95c9f5]">Storage ativo</span>
                <p className="text-sm font-semibold text-[#e6f1ff]">98.4 GB</p>
              </div>
              <div className="landing-float-chip right-3 top-24">
                <span className="text-[10px] uppercase tracking-wide text-[#95c9f5]">Tempo medio</span>
                <p className="text-sm font-semibold text-[#e6f1ff]">3 cliques</p>
              </div>
              <div className="landing-float-chip bottom-3 left-6">
                <span className="text-[10px] uppercase tracking-wide text-[#95c9f5]">Servicos</span>
                <p className="text-sm font-semibold text-[#e6f1ff]">WMS | WMTS | WCS</p>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-3 sm:grid-cols-3">
          {proofItems.map(({ icon: Icon, title, subtitle }) => (
            <article key={title} className="landing-card group rounded-2xl border border-[#223c5d] p-4">
              <Icon className="h-5 w-5 text-[#22d3ee]" />
              <h2 className="mt-2 text-sm font-bold text-[#e6f1ff]">{title}</h2>
              <p className="mt-1 text-xs leading-relaxed text-[#9db8d8]">{subtitle}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <article className="landing-card rounded-2xl border border-[#223c5d] p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#7bb8e8]">Problema real</p>
            <h3 className="mt-2 text-2xl font-black text-[#e6f1ff]">
              Sua equipe perde tempo para localizar e distribuir imagens?
            </h3>
            <div className="mt-4 space-y-3">
              {problemSolution.map((item) => (
                <div key={item.problem} className="rounded-xl border border-[#264567] bg-[#0d1f35] p-3">
                  <p className="text-sm font-semibold text-[#f4b7b7]">Problema: {item.problem}</p>
                  <p className="mt-1 text-sm text-[#a8c3e0]">Solucao: {item.solution}</p>
                </div>
              ))}
            </div>
          </article>

          <article className="landing-card rounded-2xl border border-[#223c5d] p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#7bb8e8]">Fluxo de valor</p>
            <h3 className="mt-2 text-2xl font-black text-[#e6f1ff]">Da ingestao ao compartilhamento em minutos</h3>
            <div className="mt-4 grid gap-3">
              {executionSteps.map(({ icon: Icon, title, detail }) => (
                <div key={title} className="rounded-xl border border-[#264567] bg-[#0d1f35] p-3">
                  <div className="flex items-start gap-2">
                    <Icon className="mt-0.5 h-4 w-4 text-[#22d3ee]" />
                    <div>
                      <p className="text-sm font-semibold text-[#e6f1ff]">{title}</p>
                      <p className="mt-1 text-xs text-[#9db8d8]">{detail}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section className="landing-panel rounded-3xl border border-[#1c3150] p-6 sm:p-7">
          <div className="grid items-center gap-5 lg:grid-cols-[1fr_1fr]">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-[#7bb8e8]">Demonstracao operacional</p>
              <h3 className="mt-2 text-2xl font-black text-[#e6f1ff]">Painel de uso e custos para decisao gerencial</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#9eb9d9]">
                Monitore ocupacao, crescimento e custo estimado por tenant para escalar com previsibilidade.
              </p>
              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full border border-[#2d4f78] bg-[#10243e] px-3 py-1 text-[#9fd8ff]">Storage KPI</span>
                <span className="rounded-full border border-[#2d4f78] bg-[#10243e] px-3 py-1 text-[#9fd8ff]">Billing</span>
                <span className="rounded-full border border-[#2d4f78] bg-[#10243e] px-3 py-1 text-[#9fd8ff]">Top arquivos</span>
              </div>
            </div>

            <div className="landing-demo-card rounded-2xl border border-[#28486b] p-4">
              <div className="grid grid-cols-3 gap-2">
                <MetricBox title="Arquivos" value="1.284" />
                <MetricBox title="Storage" value="2.4 TB" />
                <MetricBox title="Custo mes" value="R$ 3.420" />
              </div>
              <div className="mt-3 rounded-xl border border-[#2d4f78] bg-[#0a1a2c] p-3">
                <div className="mb-2 flex items-center justify-between text-[11px] text-[#9db8d8]">
                  <span>Evolucao de consumo</span>
                  <span>30 dias</span>
                </div>
                <div className="landing-chart-bars h-24 rounded-lg border border-[#213f5f] bg-[#0c2036] p-2">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {differentiators.map(({ icon: Icon, title, detail }) => (
            <article key={title} className="landing-card rounded-2xl border border-[#223c5d] p-4">
              <Icon className="h-5 w-5 text-[#22d3ee]" />
              <h4 className="mt-2 text-sm font-bold text-[#e6f1ff]">{title}</h4>
              <p className="mt-1 text-xs leading-relaxed text-[#9db8d8]">{detail}</p>
            </article>
          ))}
        </section>

        <section className="landing-panel rounded-3xl border border-[#1c3150] p-6 text-center sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-wide text-[#7bb8e8]">Pronto para comecar</p>
          <h5 className="mx-auto mt-2 max-w-3xl text-2xl font-black text-[#e6f1ff] sm:text-3xl">
            Comece agora e tenha controle total das suas imagens de sensoriamento remoto
          </h5>
          <p className="mx-auto mt-3 max-w-2xl text-sm text-[#9eb9d9]">
            Crie sua conta, publique sua primeira camada e veja valor real em poucos minutos.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link
              href="/cadastro"
              className="landing-btn-primary inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold"
            >
              Teste gratis e publique agora
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/acesso"
              className="landing-btn-secondary inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold"
            >
              Ja tenho conta
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

function MetricBox({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#2b4a6e] bg-[#0a1b2f] p-2">
      <p className="text-[10px] uppercase tracking-wide text-[#89b6df]">{title}</p>
      <p className="mt-1 text-sm font-semibold text-[#e6f1ff]">{value}</p>
    </div>
  );
}
