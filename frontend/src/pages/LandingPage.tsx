import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ChevronRight,
  FileCode2,
  Globe,
  Lock,
  Shield,
  ShieldCheck,
  ShieldAlert,
  Zap,
  AlertTriangle,
  ArrowUpRight,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { usePageTitle } from '@/lib/pageTitle'
import { useCountUp } from '@/lib/useCountUp'

// -------------------------------------------------------------------
// Scroll animation hook — IntersectionObserver toggling a CSS class
// -------------------------------------------------------------------

function useScrollReveal() {
  useEffect(() => {
    const sections = document.querySelectorAll('.reveal')
    if (sections.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('revealed')
          }
        })
      },
      { threshold: 0.15 },
    )

    sections.forEach((s) => observer.observe(s))
    return () => observer.disconnect()
  }, [])
}



// -------------------------------------------------------------------
// Section wrapper with fade+rise animation
// -------------------------------------------------------------------

function RevealSection({
  children,
  className = '',
  id,
}: {
  children: ReactNode
  className?: string
  id?: string
}) {
  return (
    <section
      id={id}
      className={`reveal opacity-0 translate-y-6 transition-all duration-700 ease-out ${className}`}
    >
      {children}
    </section>
  )
}

// -------------------------------------------------------------------
// Nav bar
// -------------------------------------------------------------------

function LandingNav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        {/* Brand */}
        <a href="#" className="flex items-center gap-2.5">
          <Lock className="size-5 text-accent" />
          <span className="text-base font-semibold tracking-tight text-foreground">
            ECDAT
          </span>
        </a>

        {/* Nav links */}
        <div className="hidden items-center gap-6 md:flex">
          <a
            href="#threat"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Threat
          </a>
          <a
            href="#how-it-works"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            How it works
          </a>
          <a
            href="#platform"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Platform
          </a>
        </div>

        {/* CTA */}
        <Button asChild size="sm">
          <Link to="/app/scans">Open Dashboard</Link>
        </Button>
      </div>
    </nav>
  )
}

// -------------------------------------------------------------------
// Hero section
// -------------------------------------------------------------------

function HeroConsole() {
  return (
    <div className="rounded-lg border border-border bg-surface p-5 font-mono text-sm shadow-xl">
      {/* Header bar */}
      <div className="mb-4 flex items-center gap-2">
        <span className="relative flex size-2.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-75" />
          <span className="relative inline-flex size-2.5 rounded-full bg-accent" />
        </span>
        <span className="text-xs text-muted-foreground">scan complete</span>
      </div>

      {/* Output lines */}
      <div className="space-y-1.5 text-foreground/80">
        <div className="text-muted-foreground">$ ecdat scan ./my-project</div>
        <div>
          Target: <span className="text-foreground">./my-project</span>
        </div>
        <div>
          Files scanned: <span className="text-foreground">4</span>
        </div>
        <div>
          Detections: <span className="text-foreground">13</span>
        </div>
        <div className="my-2 border-t border-border" />
        <div>
          <span className="text-red-400">critical</span>{' '}
          <span className="float-right">6</span>
        </div>
        <div>
          <span className="text-green-400">quantum-safe</span>{' '}
          <span className="float-right">7</span>
        </div>
        <div className="my-2 border-t border-border" />
        <div className="text-muted-foreground">
          CBOM exported:{' '}
          <span className="text-accent">cbom.json (CycloneDX 1.6)</span>
        </div>
      </div>
    </div>
  )
}

function Hero() {
  return (
    <RevealSection className="pt-28 pb-20" id="hero">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          {/* Text */}
          <div>
            <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              Discover every{' '}
              <span className="text-accent-soft">cryptographic asset</span>{' '}
              before quantum computing breaks it.
            </h1>
            <p className="mt-5 max-w-lg text-lg text-muted-foreground">
              ECDAT scans your source code and dependency manifests, discovers
              cryptographic artefacts, scores their post-quantum risk using
              Mosca's inequality, recommends NIST PQC replacements, and exports
              a real CycloneDX 1.6 CBOM.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button asChild size="lg">
                <Link to="/app/scans">
                  Open Dashboard
                  <ArrowRight className="ml-2 size-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <a href="#how-it-works">See how it works</a>
              </Button>
            </div>

            {/* Feature chips */}
            <div className="mt-8 flex flex-wrap gap-2 text-xs text-muted-foreground">
              {[
                'CycloneDX 1.6 CBOM',
                'Mosca\'s inequality risk scoring',
                'NIST FIPS 203 / 204 / 205',
                'Classically broken vs quantum vulnerable',
              ].map((chip) => (
                <span
                  key={chip}
                  className="rounded-full border border-border px-3 py-1"
                >
                  {chip}
                </span>
              ))}
            </div>
          </div>

          {/* Console card */}
          <div className="hidden lg:block">
            <HeroConsole />
          </div>
        </div>
      </div>
    </RevealSection>
  )
}

// -------------------------------------------------------------------
// Threat section — 4 stat cards
// -------------------------------------------------------------------

function ThreatStat({
  value,
  label,
  sub,
}: {
  value: string
  label: string
  sub: string
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <div className="text-3xl font-bold text-accent-soft">{value}</div>
      <div className="mt-2 text-sm font-medium">{label}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
    </div>
  )
}

function CountStat({
  target,
  suffix,
  label,
  sub,
}: {
  target: number
  suffix: string
  label: string
  sub: string
}) {
  const ref = useCountUp(target)
  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <div className="text-3xl font-bold text-accent-soft">
        <span ref={ref}>0</span>
        {suffix}
      </div>
      <div className="mt-2 text-sm font-medium">{label}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
    </div>
  )
}

function ThreatSection() {
  return (
    <RevealSection className="py-20" id="threat">
      <div className="mx-auto max-w-6xl px-6">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-bold tracking-tight">The Threat</h2>
          <p className="mt-3 max-w-2xl mx-auto text-muted-foreground">
            Quantum computing is not a theoretical future risk — it is an
            engineering timeline. Cryptographic migration takes years. The
            deadline to start is now.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <CountStat
            target={2030}
            suffix=""
            label="NIST CNSA 2.0 key-establishment deadline"
            sub="All new key-establishment systems must use PQC algorithms by 2030."
          />
          <CountStat
            target={2031}
            suffix=""
            label="Digital-signature migration deadline"
            sub="Existing signatures must transition to post-quantum equivalents."
          />
          <ThreatStat
            value="HNDL"
            label="Harvest now, decrypt later"
            sub="Adversaries collect encrypted data today to decrypt once quantum computers are available."
          />
          <ThreatStat
            value="10–15 yr"
            label="Cryptographic shelf life"
            sub="The data you encrypt today may still need protection in 10–15 years — well beyond the quantum horizon."
          />
        </div>
      </div>
    </RevealSection>
  )
}

// -------------------------------------------------------------------
// How it works — 3 numbered pipeline steps
// -------------------------------------------------------------------

const PIPELINE_STEPS = [
  {
    num: '01',
    title: 'Discover',
    icon: FileCode2,
    desc: 'Regex and signature-based scanning across source code files and dependency manifests. Detects RSA, ECC, DSA, AES, DES, MD5, SHA-1, and more — in both the cryptography and PyCryptodome Python libraries.',
  },
  {
    num: '02',
    title: 'Assess',
    icon: ShieldAlert,
    desc: "Scores every artefact's quantum risk using Mosca's inequality: migration time (X) + data shelf life (Y) vs. threat horizon (Z). Distinctly classifies classically broken artefacts (MD5, DES) from genuinely quantum-vulnerable ones (RSA, ECC).",
  },
  {
    num: '03',
    title: 'Recommend',
    icon: ShieldCheck,
    desc: 'Maps vulnerable algorithms to NIST PQC replacements — ML-KEM (FIPS 203), ML-DSA (FIPS 204), SLH-DSA (FIPS 205). Exports the full results as a real CycloneDX 1.6 CBOM.',
  },
]

function HowItWorks() {
  return (
    <RevealSection className="py-20" id="how-it-works">
      <div className="mx-auto max-w-6xl px-6">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-bold tracking-tight">How it works</h2>
          <p className="mt-3 max-w-2xl mx-auto text-muted-foreground">
            Three steps from source code to post-quantum readiness assessment.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {PIPELINE_STEPS.map((step) => {
            const Icon = step.icon
            return (
              <div
                key={step.num}
                className="relative rounded-lg border border-border bg-surface p-6"
              >
                <div className="mb-4 flex items-center gap-3">
                  <span className="text-2xl font-bold text-accent-soft">
                    {step.num}
                  </span>
                  <Icon className="size-5 text-accent" />
                </div>
                <h3 className="text-lg font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {step.desc}
                </p>
              </div>
            )
          })}
        </div>
      </div>
    </RevealSection>
  )
}

// -------------------------------------------------------------------
// Platform — feature grid
// -------------------------------------------------------------------

const PLATFORM_FEATURES = [
  {
    icon: FileCode2,
    title: 'Full CBOM',
    desc: 'CycloneDX 1.6 CBOM JSON export — the OWASP/Ecma standard for cryptographic bill of materials.',
  },
  {
    icon: Shield,
    title: 'Classically broken vs quantum-vulnerable',
    desc: "Most naive scanners conflate the two. ECDAT explicitly distinguishes artefacts that are already broken today (MD5, DES) from those broken by quantum computing (RSA, ECC).",
  },
  {
    icon: Lock,
    title: 'Local-first',
    desc: 'Self-hosted by design. Source code never leaves the machine it is deployed on.',
  },
  {
    icon: Globe,
    title: 'Audit-ready exports',
    desc: 'Download the CBOM JSON and a summary report — ready for compliance documentation.',
  },
  {
    icon: Zap,
    title: 'Per-artefact overrides',
    desc: 'Override shelf-life and migration-time assumptions per artefact — the risk engine re-runs live.',
  },
  {
    icon: AlertTriangle,
    title: 'Mosca\'s inequality scoring',
    desc: 'Quantitative risk scores based on (X + Y) / Z — migration time, shelf life, and threat horizon. Not just a binary label.',
  },
]

function Platform() {
  return (
    <RevealSection className="py-20" id="platform">
      <div className="mx-auto max-w-6xl px-6">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-bold tracking-tight">Platform</h2>
          <p className="mt-3 max-w-2xl mx-auto text-muted-foreground">
            Real capabilities, no made-up features. Every claim here corresponds
            to a working implementation.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PLATFORM_FEATURES.map((f) => {
            const Icon = f.icon
            return (
              <div
                key={f.title}
                className="rounded-lg border border-border bg-surface p-6 transition-colors hover:border-accent/40"
              >
                <Icon className="mb-3 size-5 text-accent" />
                <h3 className="text-sm font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                  {f.desc}
                </p>
              </div>
            )
          })}
        </div>
      </div>
    </RevealSection>
  )
}

// -------------------------------------------------------------------
// Inside the console teaser
// -------------------------------------------------------------------

function ConsoleTeaser() {
  return (
    <RevealSection className="py-20">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
          {/* Mock console — simplified static version of the hero card */}
          <div className="rounded-lg border border-border bg-surface p-5 font-mono text-sm shadow-xl">
            <div className="mb-4 flex items-center gap-2">
              <span className="size-2 rounded-full bg-accent" />
              <span className="text-xs text-muted-foreground">
                scan overview
              </span>
            </div>
            <div className="space-y-1 text-foreground/80">
              <div>
                Scan ID:{' '}
                <span className="text-foreground">0e9dd431</span>
              </div>
              <div>
                Target:{' '}
                <span className="text-foreground">demo-repo</span>
              </div>
              <div>
                Status:{' '}
                <span className="text-green-400">done</span>
              </div>
              <div className="my-2 border-t border-border" />
              <div>
                Quantum-vulnerable:{' '}
                <span className="text-amber-400">1 / 13 (7.7%)</span>
              </div>
              <div>
                Classically broken:{' '}
                <span className="text-red-400">5 / 13</span>
              </div>
              <div className="my-2 border-t border-border" />
              <div className="text-xs text-muted-foreground">
                Artefacts, recommendations, CBOM export — all in the dashboard.
              </div>
            </div>
          </div>

          {/* Text */}
          <div>
            <h2 className="text-3xl font-bold tracking-tight">
              Inside the console
            </h2>
            <p className="mt-4 text-muted-foreground">
              The dashboard gives you a full scan overview, a filterable
              artefact table with per-row risk details, grouped PQC
              recommendations, and one-click CBOM download.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-muted-foreground">
              <li className="flex items-start gap-2">
                <ChevronRight className="mt-0.5 size-4 shrink-0 text-accent" />
                Risk distribution chart and top-5 urgency list
              </li>
              <li className="flex items-start gap-2">
                <ChevronRight className="mt-0.5 size-4 shrink-0 text-accent" />
                Per-artefact Mosca's inequality timeline
              </li>
              <li className="flex items-start gap-2">
                <ChevronRight className="mt-0.5 size-4 shrink-0 text-accent" />
                Override shelf-life and migration-time, re-score live
              </li>
              <li className="flex items-start gap-2">
                <ChevronRight className="mt-0.5 size-4 shrink-0 text-accent" />
                Download CycloneDX 1.6 CBOM and summary report
              </li>
            </ul>
            <div className="mt-8">
              <Button asChild size="lg">
                <Link to="/app/scans">
                  Explore the dashboard
                  <ArrowRight className="ml-2 size-4" />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </RevealSection>
  )
}

// -------------------------------------------------------------------
// FAQ
// -------------------------------------------------------------------

const FAQ_ITEMS = [
  {
    q: 'Does ECDAT need access to my private keys?',
    a: 'No. ECDAT performs static analysis only — it scans source code files and dependency manifests. It never accesses, stores, or transmits private keys, certificates, or any secrets.',
  },
  {
    q: 'Which PQC algorithms does it recommend?',
    a: 'ECDAT maps vulnerable algorithms to the three NIST post-quantum standards: ML-KEM (FIPS 203) for key encapsulation, ML-DSA (FIPS 204) for digital signatures, and SLH-DSA (FIPS 205) for hash-based signatures.',
  },
  {
    q: 'What format does it export?',
    a: 'CycloneDX 1.6 CBOM (CycloneDX Bill of Materials) in JSON — the OWASP/Ecma standard for software composition and cryptographic asset documentation.',
  },
  {
    q: 'Is this hosted or self-hosted?',
    a: 'Self-hosted by design. ECDAT runs entirely on your own infrastructure. Source code never leaves the machine it is deployed on.',
  },
  {
    q: 'What is Mosca\'s inequality?',
    a: "It is a formula for estimating whether a cryptographic system's remaining security is still viable: (X + Y) / Z, where X is migration time, Y is data shelf life, and Z is the threat horizon. When the ratio exceeds 1.0, the data is at risk.",
  },
  {
    q: 'Can I override risk assumptions for specific artefacts?',
    a: 'Yes. The dashboard lets you override shelf-life and migration-time per artefact. The risk engine re-runs the Mosca calculation live with your updated assumptions.',
  },
]

function FAQ() {
  return (
    <RevealSection className="py-20">
      <div className="mx-auto max-w-3xl px-6">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-bold tracking-tight">
            Frequently asked questions
          </h2>
        </div>

        <Accordion type="single" collapsible className="space-y-2">
          {FAQ_ITEMS.map((item, i) => (
            <AccordionItem
              key={i}
              value={`faq-${i}`}
              className="rounded-lg border border-border bg-surface px-5"
            >
              <AccordionTrigger className="text-sm font-medium hover:no-underline">
                {item.q}
              </AccordionTrigger>
              <AccordionContent className="text-sm text-muted-foreground">
                {item.a}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </RevealSection>
  )
}

// -------------------------------------------------------------------
// Final CTA band
// -------------------------------------------------------------------

function CtaBand() {
  return (
    <RevealSection className="py-20">
      <div className="mx-auto max-w-6xl px-6 text-center">
        <h2 className="text-3xl font-bold tracking-tight">
          Ready to assess your post-quantum risk?
        </h2>
        <p className="mt-3 text-muted-foreground">
          Scan your codebase in minutes. No account required.
        </p>
        <div className="mt-8">
          <Button asChild size="lg">
            <Link to="/app/scans">
              Open Dashboard
              <ArrowRight className="ml-2 size-4" />
            </Link>
          </Button>
        </div>
      </div>
    </RevealSection>
  )
}

// -------------------------------------------------------------------
// Footer
// -------------------------------------------------------------------

function Footer() {
  return (
    <footer className="border-t border-border py-12">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-8 sm:grid-cols-3">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2">
              <Lock className="size-4 text-accent" />
              <span className="text-sm font-semibold">ECDAT</span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Cryptography Bill of Materials scanner for post-quantum readiness
              assessment.
            </p>
          </div>

          {/* Product links */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-foreground/40">
              Product
            </h4>
            <ul className="mt-3 space-y-2 text-sm">
              <li>
                <Link to="/app/scans" className="text-muted-foreground hover:text-foreground transition-colors">
                  Scanning
                </Link>
              </li>
              <li>
                <a href="#platform" className="text-muted-foreground hover:text-foreground transition-colors">
                  CBOM Export
                </a>
              </li>
              <li>
                <a href="#how-it-works" className="text-muted-foreground hover:text-foreground transition-colors">
                  Recommendations
                </a>
              </li>
            </ul>
          </div>

          {/* Resources links */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-foreground/40">
              Resources
            </h4>
            <ul className="mt-3 space-y-2 text-sm">
              <li>
                <a
                  href="https://github.com/Pratyay360/ECDAT"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
                >
                  GitHub repo
                  <ArrowUpRight className="size-3" />
                </a>
              </li>
              <li>
                <a
                  href="https://csrc.nist.gov/projects/post-quantum-cryptography"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
                >
                  NIST PQC standards
                  <ArrowUpRight className="size-3" />
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t border-border pt-6 text-center text-xs text-muted-foreground">
          Built for Smart India Hackathon 2026 &middot; Problem Statement 26164
        </div>
      </div>
    </footer>
  )
}

// -------------------------------------------------------------------
// Landing page
// -------------------------------------------------------------------

export default function LandingPage() {
  usePageTitle('Post-quantum cryptographic readiness')

  // Attach scroll-reveal animation
  useScrollReveal()

  return (
    <div className="min-h-screen bg-background text-foreground">
      <LandingNav />

      <Hero />
      <ThreatSection />
      <HowItWorks />
      <Platform />
      <ConsoleTeaser />
      <FAQ />
      <CtaBand />
      <Footer />
    </div>
  )
}
